import numpy as np
import pandas as pd

from quant.backtest.strategies import buy_and_hold, month_ends, sma_timing


def _monthly_px(vals, start="2020-01-01"):
    idx = pd.date_range(start, periods=len(vals) * 21, freq="B")
    return pd.Series(np.repeat(vals, 21), index=idx, dtype=float)


def test_sma_timing_signal():
    vals = list(np.linspace(100, 200, 12)) + [120, 100, 80]
    px = pd.DataFrame({"A": _monthly_px(vals)})
    w = sma_timing(px, "A", months=10)
    assert w["A"].iloc[0] == 1.0
    assert w["A"].iloc[-1] == 0.0


def test_sma_timing_risk_off_gets_weight():
    vals = list(np.linspace(100, 200, 12)) + [120, 100, 80]
    s = _monthly_px(vals)
    px = pd.DataFrame({"A": s, "B": s * 0 + 50})
    w = sma_timing(px, "A", months=10, risk_off="B")
    assert w["B"].iloc[-1] == 1.0 and w["A"].iloc[-1] == 0.0


def test_weight_zero_before_listing():
    a = _monthly_px(list(np.linspace(100, 200, 30)))
    b = a.copy()
    b.iloc[: 20 * 21] = np.nan
    px = pd.DataFrame({"A": a, "B": b})
    w = buy_and_hold(px, {"A": 0.5, "B": 0.5})
    assert w["B"].iloc[0] == 0.0
    assert len(month_ends(px)) == px.index.to_period("M").nunique()
