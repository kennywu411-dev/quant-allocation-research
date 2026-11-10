import numpy as np
import pandas as pd

from quant.backtest import costs
from quant.backtest.engine import run_backtest


def _idx(n):
    return pd.date_range("2024-01-01", periods=n, freq="B")


def test_blocked_sell_large_cheap_buy_never_negative_cash():
    # C1：卖单被跌停挡住，同时要大额买入低价标的，现金不能为负
    idx = _idx(5)
    px = pd.DataFrame({"511010": [100.0, 100.0, 100.0, 90.0, 90.0],
                       "510300": [1.0] * 5}, index=idx)
    w = pd.DataFrame({"511010": [1.0, 0.0], "510300": [0.0, 1.0]}, index=[idx[0], idx[2]])
    r = run_backtest(px, w, {s: costs.cn_etf() for s in px}, initial=1_000_000.0, cn_rules=True)
    assert (r.cash >= -1e-6).all()


def test_blocked_order_carries_over_without_cn_rules():
    # I2：tradable=False 时，订单顺延到下一天
    idx = _idx(4)
    px = pd.DataFrame({"SPY": [100.0] * 4}, index=idx)
    trad = pd.DataFrame({"SPY": [True, False, True, True]}, index=idx)
    w = pd.DataFrame({"SPY": [1.0]}, index=idx[:1])
    r = run_backtest(px, w, {"SPY": costs.zero()}, tradable=trad)
    assert (r.trades["date"] == idx[2]).sum() == 1


def test_nan_price_on_exec_day_carries_over():
    idx = _idx(4)
    px = pd.DataFrame({"SPY": [100.0, np.nan, 100.0, 100.0]}, index=idx)
    w = pd.DataFrame({"SPY": [1.0]}, index=idx[:1])
    r = run_backtest(px, w, {"SPY": costs.zero()}, fractional=True)
    assert r.positions["SPY"].iloc[-1] > 0


def test_limit_down_after_suspension_detected():
    # I3：停牌一天后复牌跌停，仍不能卖
    idx = _idx(6)
    px = pd.DataFrame({"600000": [10.0, 10.0, 10.0, np.nan, 9.0, 9.0]}, index=idx)
    w = pd.DataFrame({"600000": [1.0, 0.0]}, index=[idx[0], idx[2]])
    r = run_backtest(px, w, {"600000": costs.zero(lot=100)}, initial=10000.0, cn_rules=True)
    assert r.positions["600000"].loc[idx[4]] == 1000


def test_blocked_count_and_one_sided_turnover():
    # 报告需要知道规则触发次数；换手按单边计
    idx = _idx(4)
    px = pd.DataFrame({"600000": [10.0, 11.0, 11.1, 11.1]}, index=idx)
    w = pd.DataFrame({"600000": [1.0]}, index=idx[:1])
    r = run_backtest(px, w, {"600000": costs.zero(lot=100)}, initial=11100.0, cn_rules=True)
    assert r.blocked >= 1
    years = (idx[-1] - idx[0]).days / 365.25
    assert r.turnover == (11100.0 / 2) / r.nav.mean() / years
