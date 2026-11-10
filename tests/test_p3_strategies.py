import numpy as np
import pandas as pd
import pytest

from quant.backtest import costs
from quant.backtest.strategies import rebalance_dates, static_mix, trend_mix


def _monthly(vals, start="2020-01-01"):
    idx = pd.date_range(start, periods=len(vals) * 21, freq="B")
    return pd.Series(np.repeat(vals, 21), index=idx, dtype=float)


def test_rebalance_dates_modes():
    px = pd.DataFrame({"A": 1.0}, index=pd.date_range("2024-01-01", "2024-03-29", freq="B"))
    assert rebalance_dates(px, "start")[0] == pd.Timestamp("2024-01-01")
    assert rebalance_dates(px, "mid")[0] == pd.Timestamp("2024-01-15")
    assert rebalance_dates(px, "end")[0] == pd.Timestamp("2024-01-31")


def test_trend_mix_moves_weight_to_safe_when_below_sma():
    a = _monthly(list(np.linspace(100, 200, 12)) + [120, 100, 80])
    px = pd.DataFrame({"A": a, "S": a * 0 + 50})
    d = rebalance_dates(px, "end")
    w = trend_mix(px, {"A": 0.6, "S": 0.4}, ["A"], "S", "sma10", d)
    assert w["A"].iloc[-1] == 0.0
    assert w["S"].iloc[-1] == pytest.approx(1.0)
    assert w["A"].iloc[0] == 0.6


def test_trend_mix_mom_fraction():
    # 当前价高于 3、6 个采样点前，低于 9、12 个采样点前
    vals = [300, 300, 300, 300, 300, 100, 100, 100, 100, 100, 100, 100, 150]
    px = pd.DataFrame({"A": _monthly(vals), "S": _monthly([50] * 13)})
    d = rebalance_dates(px, "end")
    w = trend_mix(px, {"A": 1.0}, ["A"], "S", "mom", d)
    assert w["A"].iloc[-1] == pytest.approx(0.5)
    assert w["S"].iloc[-1] == pytest.approx(0.5)


def test_trend_mix_safe_unlisted_goes_to_cash():
    a = _monthly(list(np.linspace(100, 200, 12)) + [120, 100, 80])
    s = a * 0 + 50
    s[:] = np.nan
    px = pd.DataFrame({"A": a, "S": s})
    d = rebalance_dates(px, "end")
    w = trend_mix(px, {"A": 1.0}, ["A"], "S", "sma10", d)
    assert w.iloc[-1].sum() == 0.0


def test_static_mix_unlisted_zero():
    a = _monthly([100] * 5)
    b = a.copy()
    b.iloc[:42] = np.nan
    px = pd.DataFrame({"A": a, "B": b})
    w = static_mix(px, {"A": 0.5, "B": 0.5}, rebalance_dates(px, "end"))
    assert w["B"].iloc[0] == 0.0 and w["B"].iloc[-1] == 0.5


def test_scaled_costs_double():
    assert costs.scaled(costs.cn_stock(), 2).cost("sell", 1000) == pytest.approx(2 * (5 + 0.5 + 1.0))
