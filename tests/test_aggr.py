import numpy as np
import pandas as pd

from quant.research import p3
from quant.research.aggr import CANDIDATES_CN, CANDIDATES_US, covers_2008, trial_names


def test_grid_size():
    us, cn = trial_names("美股账户"), trial_names("A股账户")
    assert len(us) == 36 and len(cn) == 18
    assert len(set(us)) == 36 and len(set(cn)) == 18
    assert len(CANDIDATES_US) == 6 and len(CANDIDATES_CN) == 3


def _nav(dd, cagr, idx):
    """先跌到 dd 再涨，使全期年化约为 cagr。"""
    n = len(idx)
    path = np.concatenate([np.linspace(1, 1 + dd, n // 4), np.linspace(1 + dd, (1 + cagr) ** (n / 252), n - n // 4)])
    s = pd.Series(path, index=idx)
    return {m: s for m in ("end", "mid", "start")}


def test_select_pair_custom_limit():
    idx = pd.bdate_range("2005-01-03", "2022-12-30")
    us = pd.DataFrame({"name": ["A", "B"], "eligible": [True, True]})
    cn = pd.DataFrame({"name": ["C"], "eligible": [True]})
    navs_us = {"A": _nav(-0.25, 0.09, idx), "B": _nav(-0.35, 0.12, idx)}
    navs_cn = {"C": _nav(-0.25, 0.09, idx)}
    pick30, _ = p3.select_pair(us, cn, navs_us, navs_cn, 1.0, mdd_limit=-0.30)
    pick40, _ = p3.select_pair(us, cn, navs_us, navs_cn, 1.0, mdd_limit=-0.40)
    assert pick30 == ("A", "C") and pick40 == ("B", "C")


def test_leveraged_signal_uses_index():
    idx = pd.bdate_range("2020-01-01", periods=400)
    dates = p3.rebalance_dates(pd.DataFrame(index=idx), "end")
    spy = pd.Series(np.linspace(200, 100, 400), index=idx)      # 一路下跌：均线之下
    sso = pd.Series(np.linspace(100, 300, 400), index=idx)      # 合成序列恰好向上（人为构造）
    px = pd.DataFrame({"SSO": sso, "IEF": 100.0})
    a = dict(eq=["SSO"], gold=[], safe="IEF", signal_series={"SSO": spy})
    w = p3._weights(px, {"SSO": 1.0, "IEF": 0.0}, "sma10_bond", a, dates)
    assert w.SSO.iloc[-1] == 0.0 and w.IEF.iloc[-1] == 1.0


def test_pairs_without_2008_not_selectable():
    assert covers_2008(pd.Timestamp("2007-05-31"))
    assert not covers_2008(pd.Timestamp("2011-07-29"))


def test_expensive_synthetic_held_with_fractional():
    from quant.research.aggr import account_cfg
    idx = pd.bdate_range("2010-01-01", periods=300)
    px = pd.DataFrame({"MOMBIG": np.linspace(20000, 40000, 300), "IEF": 100.0, "TLT": 100.0, "GLD": 100.0}, index=idx)
    a = account_cfg("美股账户", "MOMBIG")
    assert a.get("fractional") is True
    base = {"MOMBIG": 1.0, "IEF": 0.0, "TLT": 0.0, "GLD": 0.0}
    dates = p3.rebalance_dates(px, "end")
    w = p3._weights(px, base, "static", a, dates)
    fx = {"AUDUSD": pd.Series(1.0, index=idx), "AUDCNY": pd.Series(1.0, index=idx)}
    _, local = p3._run(px, w, a, 1.0, fx)
    assert local.iloc[-1] / local.iloc[0] > 1.5   # 价格涨了约 1 倍，组合必须跟着涨


def test_fractional_cash_never_negative_with_min_fee():
    """碎股 + 每单最低佣金：几分钱的再平衡卖单不该把现金扣成负数（真实数据 MOMBIG 曾在 2013-10-16 触发）。"""
    from quant.backtest import costs
    from quant.backtest.engine import run_backtest
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2020-01-01", periods=600)
    px = pd.DataFrame({"A": 100 * np.cumprod(1 + rng.normal(0, 0.01, 600)),
                       "B": 100 * np.cumprod(1 + rng.normal(0, 0.003, 600))}, index=idx)
    w = pd.DataFrame({"A": 0.9, "B": 0.1}, index=p3.rebalance_dates(px, "end"))
    cm = {s: costs.scaled(costs.us_etf(), 2) for s in px}
    res = run_backtest(px, w, cm, 10000.0, fractional=True)
    assert res.nav.iloc[-1] > 0


def test_run_account_phase_param():
    import inspect
    assert "phase" in inspect.signature(p3.run_account).parameters


def test_unknown_proxy_kind_raises():
    import pytest
    D5 = pd.bdate_range("2020-01-01", periods=5)
    a = dict(market="US", eq=["SSO"], bond=[], gold=[], proxy={"SSO": ("lev", "SPY")})
    gp = lambda s, m, k: pd.Series(1.0, index=D5[2:] if s == "SSO" else D5)  # noqa: E731
    with pytest.raises(ValueError, match="lev"):
        p3.build_prices(a, gp, None, {}, {})


def test_sleeve_setup_shared_config():
    from quant.research.aggr import sleeve_setup
    D5 = pd.bdate_range("2020-01-01", periods=30)
    gp = lambda s, m, k: pd.Series(np.linspace(100, 110, 30), index=D5, name=s)  # noqa: E731
    getters = {"lev": lambda code: pd.Series(np.linspace(1, 1.2, 30), index=D5)}
    a, px, notes = sleeve_setup("美股账户", "SSO", gp, None, {"AUDUSD": None}, getters)
    assert "SSO" in a["signal_series"] and a["proxy"]["SSO"] == ("lev", "SPY")
    assert "SSO" in px


def test_synthetic_not_tradable():
    import pytest
    from quant.research.aggr import assert_tradable
    with pytest.raises(ValueError, match="MOMBIG"):
        assert_tradable({"MOMBIG": 0.9, "IEF": 0.1}, {"synthetic": {"MOMBIG": ("french", "x", 0.01)}})
    assert_tradable({"QQQ": 0.9}, {})
