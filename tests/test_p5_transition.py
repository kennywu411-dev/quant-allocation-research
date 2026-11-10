import numpy as np
import pandas as pd
import pytest

from quant.backtest import costs
from quant.portfolio.transition import target_weights, tax_fields, tranche_plan, transition_orders


def _cost(s, side, v):
    return (costs.cn_stock() if s == "000651" else costs.cn_etf()).cost(side, v)


H = pd.DataFrame({"account": ["银河"], "market": ["CN"], "symbol": ["000651"], "shares": [1400.0], "ccy": ["CNY"],
                  "cost_basis": [np.nan], "buy_date": [np.nan], "note": [""]})
LOT = {"000651": 100, "510300": 100, "511010": 100}


def test_target_uses_last_complete_month_end():
    idx = pd.bdate_range("2024-01-01", "2026-10-28")
    px = pd.DataFrame({"E": np.linspace(1, 2, len(idx)), "B": np.linspace(1, 1.1, len(idx))}, idx)
    a = {"eq": ["E"], "bond": ["B"], "gold": [], "safe": "B"}
    d, w = target_weights(px, a, {"E": 0.6, "B": 0.4}, "sma10_bond", today=pd.Timestamp("2026-10-29"))
    assert d == pd.Timestamp("2026-09-30")
    assert w == pytest.approx({"E": 0.6, "B": 0.4})  # 上涨趋势，信号保留股票


def test_transition_cash_nonnegative_and_lots():
    prices = {"000651": 20.0, "510300": 4.0, "511010": 100.0}
    o = transition_orders(H, prices, {"510300": 0.5, "511010": 0.5}, "银河", LOT, _cost)
    sell = o[(o.symbol == "000651")].iloc[0]
    assert sell.side == "卖" and sell.shares == 1400
    assert sell.cost == pytest.approx(costs.cn_stock().cost("sell", 28000))
    buys = o[o.side == "买"]
    assert all(buys.shares % 100 == 0)
    cash = o[o.symbol == "CASH"].value.iloc[0]
    assert 0 <= cash < 100 * 100 + 10


def test_tranche_plan_sums():
    prices = {"000651": 20.0, "510300": 4.0, "511010": 100.0}
    o = transition_orders(H, prices, {"510300": 0.5, "511010": 0.5}, "银河", LOT, _cost)
    parts = tranche_plan(o, LOT, _cost, n=3)
    assert len(parts) == 3
    for s in ["000651", "510300", "511010"]:
        got = sum(p[p.symbol == s].shares.sum() for p in parts)
        assert got == o[o.symbol == s].shares.sum()
        assert all(p[p.symbol == s].shares.sum() % 100 == 0 for p in parts)


def test_tax_fields_missing():
    t = tax_fields(H, {"000651": 20.0}, pd.Timestamp("2026-10-31"))
    assert t.gain.iloc[0] == "待补" and t.held_days.iloc[0] == "待补"
    h = H.copy()
    h["cost_basis"], h["buy_date"] = [15.0], ["2025-10-30"]
    t = tax_fields(h, {"000651": 20.0}, pd.Timestamp("2026-10-31"))
    assert t.gain.iloc[0] == pytest.approx(7000.0)
    assert t.held_days.iloc[0] == 366 and bool(t.discount_eligible.iloc[0])
    h["buy_date"] = ["2025-10-31"]
    assert not bool(tax_fields(h, {"000651": 20.0}, pd.Timestamp("2026-10-31")).discount_eligible.iloc[0])


def _px(end):
    idx = pd.bdate_range("2023-01-02", end)
    return pd.DataFrame({"E": np.linspace(1, 2, len(idx)), "B": np.linspace(1, 1.1, len(idx))}, idx)


A = {"eq": ["E"], "bond": ["B"], "gold": [], "safe": "B"}


def test_target_holiday_month_end_counts_after_month():
    px = _px("2025-01-27")  # 春节前最后一个交易日
    d, _ = target_weights(px, A, {"E": 0.6, "B": 0.4}, "sma10_bond", today=pd.Timestamp("2025-02-03"))
    assert d == pd.Timestamp("2025-01-27")


def test_target_drops_bar_dated_today():
    px = _px("2026-10-30")
    d, _ = target_weights(px, A, {"E": 0.6, "B": 0.4}, "sma10_bond", today=pd.Timestamp("2026-10-30"))
    assert d == pd.Timestamp("2026-09-30")
    d, _ = target_weights(px, A, {"E": 0.6, "B": 0.4}, "sma10_bond", today=pd.Timestamp("2026-10-31"))
    assert d == pd.Timestamp("2026-10-30")


def test_transition_sums_lots_of_same_symbol():
    h = pd.concat([H, H]).reset_index(drop=True)
    h["shares"] = [800.0, 600.0]
    o = transition_orders(h, {"000651": 20.0, "510300": 4.0, "511010": 100.0}, {"510300": 0.5, "511010": 0.5}, "银河", LOT, _cost)
    assert o[o.symbol == "000651"].shares.iloc[0] == 1400


def test_tranche_cash_never_negative_without_starting_cash():
    h = H.copy()
    h["shares"] = [1300.0]
    lot = {"000651": 100, "510880": 100}
    prices = {"000651": 20.0, "510880": 1.0}
    o = transition_orders(h, prices, {"510880": 1.0}, "银河", lot, _cost)
    parts = tranche_plan(o, lot, _cost, n=3, cash0=0.0)
    for p in parts:
        assert p[p.symbol == "CASH"].value.iloc[0] >= 0
        assert all(p[p.side == "买"].shares % 100 == 0)
    assert sum(p[p.side == "卖"].shares.sum() for p in parts) == 1300


def test_tax_discount_leap_year_boundary():
    h = H.copy()
    h["cost_basis"], h["buy_date"] = [15.0], ["2023-03-01"]
    assert not bool(tax_fields(h, {"000651": 20.0}, pd.Timestamp("2024-03-01")).discount_eligible.iloc[0])
    assert bool(tax_fields(h, {"000651": 20.0}, pd.Timestamp("2024-03-02")).discount_eligible.iloc[0])
