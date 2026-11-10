import numpy as np
import pandas as pd
import pytest

from quant.research.p3 import build_prices
from quant.research.p4 import beats_core, factor_test, substitute


def _s(vals, start):
    return pd.Series(vals, pd.bdate_range(start, periods=len(vals)), dtype=float)


def test_substitute_keeps_sleeve_sum():
    assert substitute({"SPY": 0.6, "IEF": 0.1}, ["SPY"], ["MTUM"], 0.5) == pytest.approx({"SPY": 0.3, "MTUM": 0.3, "IEF": 0.1})
    full = substitute({"SPY": 0.6, "IEF": 0.1}, ["SPY"], ["MTUM"], 1.0)
    assert full["SPY"] == 0.0 and full["MTUM"] == pytest.approx(0.6)
    three = substitute({"SPY": 0.6}, ["SPY"], ["A", "B", "C"], 1.0)
    assert three == pytest.approx({"SPY": 0.0, "A": 0.2, "B": 0.2, "C": 0.2})


def test_build_prices_fee_drag():
    etf = _s(np.linspace(10, 12, 30), "2012-03-01")
    proxy = _s(np.full(100, 5.0), "2011-11-01")
    a = {"eq": ["E"], "bond": [], "gold": [], "market": "US", "proxy": {"E": ("flat", "P")}, "fee": {"E": 0.252}}
    px, _ = build_prices(a, get_price=lambda s, m, k: etf, get_index=None, fx={}, getters={"flat": lambda c: proxy})
    pre = px["E"].loc[:etf.index[0]]
    assert (pre.pct_change().dropna()).tolist() == pytest.approx([-0.001] * (len(pre) - 1))
    assert px["E"].loc[etf.index[0]:].tolist() == pytest.approx(etf.tolist())
    a.pop("fee")
    px2, _ = build_prices(a, get_price=lambda s, m, k: etf, get_index=None, fx={}, getters={"flat": lambda c: proxy})
    assert px2["E"].loc[:etf.index[0]].nunique() == 1


def test_factor_test_fields():
    idx = pd.bdate_range("2000-01-03", "2024-12-31")
    rng = np.random.default_rng(3)
    b = pd.Series(np.cumprod(1 + rng.normal(0.0003, 0.01, len(idx))), idx)
    s = pd.Series(np.cumprod(1 + b.pct_change().fillna(0).to_numpy() + 0.0002), idx)
    r = factor_test(s, b, n_trials=20, sr_var=0.001)
    for k in ["alpha_ann", "t_alpha", "dsr", "is_excess", "oos_excess", "passed", "start"]:
        assert k in r
    assert r["passed"] == (r["t_alpha"] >= 2.5 and r["dsr"] >= 0.95)


def test_beats_core_rule():
    core = {"is_cagr": 0.06, "oos_cagr": 0.05}
    assert beats_core({"is_cagr": 0.07, "oos_cagr": 0.05}, core)
    assert not beats_core({"is_cagr": 0.07, "oos_cagr": 0.049}, core)
    assert not beats_core({"is_cagr": 0.06, "oos_cagr": 0.08}, core)


def test_factor_test_uses_rf_and_recent_t():
    idx = pd.bdate_range("2000-01-03", "2024-12-31")
    rng = np.random.default_rng(4)
    b = pd.Series(np.cumprod(1 + rng.normal(0.0003, 0.01, len(idx))), idx)
    rf = pd.Series(np.cumprod(np.full(len(idx), 1 + 0.0002)), idx)
    s = pd.Series(np.cumprod(1 + 0.5 * b.pct_change().fillna(0).to_numpy() + 0.0001), idx)
    with_rf = factor_test(s, b, n_trials=1, sr_var=0.0, rf=rf, recent="2013-01-01")
    no_rf = factor_test(s, b, n_trials=1, sr_var=0.0)
    assert with_rf["alpha_ann"] < no_rf["alpha_ann"] - 0.01
    assert "t_recent" in with_rf and np.isfinite(with_rf["t_recent"])
