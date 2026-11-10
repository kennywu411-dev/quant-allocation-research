import numpy as np
import pandas as pd
import pytest
from statistics import NormalDist

from quant.research.stats import alpha_t, deflated_sharpe, monthly_returns


def _months(n):
    return pd.date_range("1970-01-31", periods=n, freq="ME")


def test_alpha_t_recovers_known_alpha():
    rng = np.random.default_rng(0)
    b = rng.normal(0.008, 0.04, 600)
    a = 0.002 + 1.0 * b + rng.normal(0, 0.01, 600)
    r = alpha_t(pd.Series(a, _months(600)), pd.Series(b, _months(600)))
    assert r["beta"] == pytest.approx(1.0, abs=0.05)
    assert r["alpha_ann"] == pytest.approx(0.024, abs=0.01)
    assert r["t_alpha"] > 3
    assert r["n_months"] == 600


def test_dsr_penalises_trials():
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(0.01, 0.04, 240), _months(240))
    assert deflated_sharpe(x, 1, 0.0) > deflated_sharpe(x, 100, 0.01)
    sr = x.mean() / x.std(ddof=1)
    g3 = ((x - x.mean()) ** 3).mean() / x.std(ddof=0) ** 3
    g4 = ((x - x.mean()) ** 4).mean() / x.std(ddof=0) ** 4
    psr = NormalDist().cdf(sr * np.sqrt(239) / np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2))
    assert deflated_sharpe(x, 1, 0.0) == pytest.approx(psr, abs=1e-6)


def test_monthly_returns_month_end():
    idx = pd.to_datetime(["2020-01-15", "2020-01-31", "2020-02-28", "2020-03-31"])
    r = monthly_returns(pd.Series([1.0, 1.1, 1.21, 1.21], idx))
    assert list(r) == pytest.approx([0.1, 0.0])


def test_alpha_t_subtracts_risk_free():
    # 真实 alpha 为 0、beta 0.5、无风险利率每月 0.5%：不减 rf 会得到 (1-β)·rf ≈ 3%/年的假 alpha
    rng = np.random.default_rng(2)
    rf = pd.Series(0.005, _months(600))
    b = pd.Series(rng.normal(0.008, 0.04, 600), _months(600))
    a = rf + 0.5 * (b - rf) + rng.normal(0, 0.005, 600)
    assert alpha_t(a, b)["alpha_ann"] > 0.02
    r = alpha_t(a, b, rf=rf)
    assert r["alpha_ann"] == pytest.approx(0.0, abs=0.005)
    assert r["beta"] == pytest.approx(0.5, abs=0.03)
