import numpy as np
import pandas as pd
import pytest

from quant.backtest import costs
from quant.backtest.engine import run_backtest


def _idx(n):
    return pd.date_range("2024-01-01", periods=n, freq="B")


def test_buy_and_hold_no_cost_matches_price():
    idx = _idx(50)
    px = pd.DataFrame({"A": np.linspace(100, 150, 50)}, index=idx)
    w = pd.DataFrame({"A": [1.0]}, index=idx[:1])
    r = run_backtest(px, w, {"A": costs.zero()}, fractional=True)
    nav = r.nav.loc[idx[1]:]
    ratio = nav / px["A"].loc[idx[1]:]
    assert (ratio - ratio.iloc[0]).abs().max() < 1e-9


def test_trade_executes_next_day_no_lookahead():
    idx = _idx(3)
    px = pd.DataFrame({"A": [100.0, 200.0, 200.0]}, index=idx)
    w = pd.DataFrame({"A": [1.0]}, index=idx[:1])
    r = run_backtest(px, w, {"A": costs.zero()}, initial=1000.0, fractional=True)
    assert r.trades.iloc[0]["price"] == 200.0
    assert r.nav.iloc[-1] == pytest.approx(1000.0)


def test_lot_rounding_leaves_cash_never_negative():
    idx = _idx(5)
    px = pd.DataFrame({"A": [300.0] * 5}, index=idx)
    w = pd.DataFrame({"A": [1.0]}, index=idx[:1])
    r = run_backtest(px, w, {"A": costs.zero(lot=100)}, initial=20000.0)
    assert r.positions["A"].iloc[-1] == 0
    assert (r.cash >= 0).all()
    assert r.cash.iloc[-1] == 20000.0


def test_costs_us_per_order_and_cn_min():
    assert costs.us_etf().cost("buy", 1000) == pytest.approx(0.99 + 0.5)
    assert costs.cn_stock().cost("sell", 1000) == pytest.approx(5 + 0.5 + 1.0)
