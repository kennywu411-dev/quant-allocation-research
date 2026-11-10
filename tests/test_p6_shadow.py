import pandas as pd
import pytest

from quant.live.shadow import init_shadow, load_state, mark, rebalance, save_state
from quant.research.p5 import cost_fn

D = pd.Timestamp
ZERO = lambda s, side, v: 0.0  # noqa: E731


def test_rebalance_once_per_month():
    st = init_shadow("美股账户", 10000.0, D("2026-11-02"))
    st = rebalance(st, "2026-11", {"SPY": 0.6, "IEF": 0.4}, {"SPY": 100.0, "IEF": 100.0}, {"SPY": 1, "IEF": 1}, ZERO)
    snap = (dict(st["positions"]), st["cash"])
    st = rebalance(st, "2026-11", {"SPY": 0.0, "IEF": 1.0}, {"SPY": 100.0, "IEF": 100.0}, {"SPY": 1, "IEF": 1}, ZERO)
    assert (dict(st["positions"]), st["cash"]) == snap
    assert len(st["history"]) == 1
    assert st["positions"] == {"SPY": 60, "IEF": 40}


def test_rebalance_costs_and_lots():
    st = init_shadow("A股账户", 100000.0, D("2026-11-02"))
    st = rebalance(st, "2026-11", {"510880": 0.15, "511010": 0.85}, {"510880": 3.46, "511010": 141.12},
                   {"510880": 100, "511010": 100}, cost_fn("A股账户"))
    assert all(q % 100 == 0 for q in st["positions"].values())
    assert st["cash"] >= 0
    fills = st["history"][0]["orders"]
    assert sum(o["cost"] for o in fills) > 0


def test_mark_value(tmp_path):
    st = init_shadow("美股账户", 10000.0, D("2026-11-02"))
    st = rebalance(st, "2026-11", {"SPY": 0.6, "IEF": 0.4}, {"SPY": 100.0, "IEF": 100.0}, {"SPY": 1, "IEF": 1}, ZERO)
    st = mark(st, D("2026-11-03"), {"SPY": 110.0, "IEF": 100.0})
    st = mark(st, D("2026-11-03"), {"SPY": 110.0, "IEF": 100.0})
    assert st["marks"] == [{"date": "2026-11-03", "price_date": "2026-11-03", "value": pytest.approx(60 * 110 + 40 * 100)}]
    save_state(st, tmp_path / "s.json")
    assert load_state(tmp_path / "s.json") == st


def test_price_date_recorded():
    st = init_shadow("美股账户", 10000.0, D("2026-11-02"))
    st = rebalance(st, "2026-11", {"SPY": 1.0}, {"SPY": 100.0}, {"SPY": 1}, ZERO, D("2026-11-02"), D("2026-10-30"))
    st = mark(st, D("2026-11-02"), {"SPY": 100.0}, D("2026-10-30"))
    assert st["history"][0]["price_date"] == "2026-10-30"
    assert st["marks"][0]["price_date"] == "2026-10-30"
