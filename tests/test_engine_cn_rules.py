import pandas as pd

from quant.backtest import costs
from quant.backtest.engine import limit_pct, run_backtest


def _idx(n):
    return pd.date_range("2024-01-01", periods=n, freq="B")


def _w(idx):
    return pd.DataFrame({"600000": [1.0]}, index=idx[:1])


def test_limit_up_blocks_buy_then_fills_next_day():
    idx = _idx(4)
    px = pd.DataFrame({"600000": [10.0, 11.0, 11.1, 11.1]}, index=idx)  # 第 1 天涨停
    r = run_backtest(px, _w(idx), {"600000": costs.zero(lot=100)}, cn_rules=True)
    assert (r.trades["date"] == idx[1]).sum() == 0
    assert (r.trades["date"] == idx[2]).sum() == 1


def test_limit_down_blocks_sell_position_keeps_loss():
    idx = _idx(5)
    px = pd.DataFrame({"600000": [10.0, 10.0, 10.0, 9.0, 9.0]}, index=idx)
    w = pd.DataFrame({"600000": [1.0, 0.0]}, index=[idx[0], idx[2]])  # 第 3 天应卖出，但跌停
    r = run_backtest(px, w, {"600000": costs.zero(lot=100)}, initial=10000.0, cn_rules=True)
    assert r.positions["600000"].loc[idx[3]] == 1000
    assert r.nav.loc[idx[3]] == 9000.0
    assert r.positions["600000"].loc[idx[4]] == 0


def test_suspended_day_no_trade():
    idx = _idx(4)
    px = pd.DataFrame({"600000": [10.0, 10.0, 10.0, 10.0]}, index=idx)
    trad = pd.DataFrame({"600000": [True, False, True, True]}, index=idx)
    r = run_backtest(px, _w(idx), {"600000": costs.zero(lot=100)}, cn_rules=True, tradable=trad)
    assert (r.trades["date"] == idx[1]).sum() == 0
    assert (r.trades["date"] == idx[2]).sum() == 1


def test_limit_pct_by_board():
    assert limit_pct("300750") == 0.2
    assert limit_pct("600000") == 0.1
    assert limit_pct("688981") == 0.2
