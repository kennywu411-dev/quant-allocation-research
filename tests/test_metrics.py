import numpy as np
import pandas as pd

from quant.metrics import max_drawdown, worst_drawdowns


def _nav(vals):
    return pd.Series(vals, index=pd.date_range("2024-01-01", periods=len(vals)), dtype=float)


def test_max_drawdown_simple():
    assert max_drawdown(_nav([100, 120, 90, 130])) == -0.25


def test_split_adjusted_no_fake_drawdown():
    # 复权价应当平滑；这条测试记录"必须用复权价"的约定
    nav = _nav(np.linspace(100, 200, 300))
    assert max_drawdown(nav) > -0.01


def test_worst_drawdowns_unrecovered():
    nav = _nav([100, 80, 110, 120, 90, 95])
    w = worst_drawdowns(nav, n=5)
    assert w.iloc[0]["depth"] == -0.25
    assert pd.isna(w.iloc[0]["recovery"])
    assert len(w) == 2


def test_sharpe_constant_excess_and_rf():
    from quant.metrics import sharpe
    idx = pd.bdate_range("2020-01-01", periods=505)
    r = pd.Series(np.where(np.arange(505) % 2, 0.002, 0.0), index=idx)
    nav = (1 + r).cumprod()
    rf = pd.Series(1.0, index=idx)  # 无风险收益为 0
    ex = r.iloc[1:]
    assert abs(sharpe(nav, rf) - ex.mean() / ex.std() * np.sqrt(252)) < 1e-9
    rf2 = (1 + pd.Series(0.001, index=idx)).cumprod()  # 每天 0.1% 的无风险收益
    ex2 = (r - 0.001).iloc[1:]
    assert abs(sharpe(nav, rf2) - ex2.mean() / ex2.std() * np.sqrt(252)) < 1e-9


def test_calmar():
    from quant.metrics import calmar
    idx = pd.to_datetime(["2020-01-01", "2021-01-01", "2022-01-01"])
    nav = pd.Series([1.0, 0.8, 1.21], index=idx)
    years = (idx[-1] - idx[0]).days / 365.25
    assert abs(calmar(nav) - (1.21 ** (1 / years) - 1) / 0.2) < 1e-12
