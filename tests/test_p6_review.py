import pandas as pd
import pytest

from quant.live.review import decompose, followed, render, slippage


def test_decompose_sums_to_total():
    d = decompose(shadow_ret=0.012, backtest_ret=0.018, ideal_ret=0.02, shadow_cost=0.001)
    parts = sum(v for k, v in d.items() if k != "合计")
    assert parts == pytest.approx(d["合计"], abs=1e-12)
    assert d["合计"] == pytest.approx(0.012 - 0.018)
    assert d["影子盘成本"] == pytest.approx(-0.001)


def test_slippage_sign():
    log = pd.DataFrame([{"order_id": "A", "symbol": "SPY", "side": "买", "shares": 10, "ref_price": 100.0},
                        {"order_id": "B", "symbol": "TLT", "side": "卖", "shares": 5, "ref_price": 80.0},
                        {"order_id": "C", "symbol": "IEF", "side": "买", "shares": 4, "ref_price": 90.0}])
    fills = pd.DataFrame([{"order_id": "A", "status": "FILLED_ALL", "qty": 10, "dealt_qty": 10, "dealt_avg_price": 100.5},
                          {"order_id": "B", "status": "FILLED_ALL", "qty": 5, "dealt_qty": 5, "dealt_avg_price": 79.0},
                          {"order_id": "C", "status": "CANCELLED_PART", "qty": 4, "dealt_qty": 1, "dealt_avg_price": 90.0}])
    s = slippage(log, fills).set_index("order_id")
    assert s.loc["A", "slip_value"] == pytest.approx(-5.0)   # 买贵了
    assert s.loc["B", "slip_value"] == pytest.approx(-5.0)   # 卖便宜了
    assert s.loc["C", "unfilled_value"] == pytest.approx(3 * 90.0)


def test_not_followed_separated():
    before = pd.DataFrame([{"account": "moomoo", "symbol": "AAPL", "shares": 7},
                           {"account": "moomoo", "symbol": "MSFT", "shares": 3}])
    after = pd.DataFrame([{"account": "moomoo", "symbol": "MSFT", "shares": 3},
                          {"account": "moomoo", "symbol": "SPY", "shares": 5}])
    orders = pd.DataFrame([{"symbol": "AAPL", "side": "卖", "shares": 7}, {"symbol": "MSFT", "side": "卖", "shares": 3},
                           {"symbol": "SPY", "side": "买", "shares": 14}, {"symbol": "CASH", "side": "剩余", "shares": 0}])
    f = followed(before, after, orders, "moomoo").set_index("symbol")
    assert f.loc["AAPL", "状态"] == "已执行"
    assert f.loc["MSFT", "状态"] == "没照做"
    assert f.loc["SPY", "状态"] == "部分执行"
    assert "CASH" not in f.index


def test_render_sections():
    acc = {"window": "2026-11-02 至 2026-11-30", "ccy": "USD",
           "decomp": decompose(0.012, 0.018, 0.02, 0.001),
           "slip": pd.DataFrame(columns=["order_id", "symbol", "side", "slip_value", "unfilled_value"]),
           "followed": pd.DataFrame([{"symbol": "AAPL", "计划": -7, "实际": 0, "状态": "没照做"}])}
    md = render({"month": "2026-11", "months_recorded": 1, "accounts": {"美股账户": acc}})
    for h in ["偏差拆解", "没照做", "影子盘", "模拟盘", "声明", "记录未满 3 个月"]:
        assert h in md, h


def test_window_adds_back_next_rebalance_cost_and_uses_price_dates():
    from quant.live.review import _window
    st = {"history": [{"month": "2026-11", "date": "2026-11-02", "price_date": "2026-10-30", "orders": [{"cost": 5.0}]},
                      {"month": "2026-12", "date": "2026-12-01", "price_date": "2026-11-30", "orders": [{"cost": 3.0}]}],
          "marks": [{"date": "2026-11-02", "value": 995.0}, {"date": "2026-12-01", "value": 1097.0}]}
    h, p0, p1, v0, v1 = _window(st, "2026-11")
    assert v0 == 1000.0 and v1 == 1100.0
    assert p0 == pd.Timestamp("2026-10-30") and p1 == pd.Timestamp("2026-11-30")


def test_unmatched_paper_order_marked():
    log = pd.DataFrame([{"order_id": "Z", "symbol": "SPY", "side": "买", "shares": 2, "ref_price": 100.0}])
    fills = pd.DataFrame(columns=["order_id", "status", "qty", "dealt_qty", "dealt_avg_price"])
    s = slippage(log, fills)
    assert s.status.iloc[0] == "未查到"


def test_prev_month():
    from quant.live.review import prev_month
    assert prev_month(pd.Timestamp("2026-11-04")) == "2026-10"
    assert prev_month(pd.Timestamp("2026-11-01")) == "2026-10"
    assert prev_month(pd.Timestamp("2027-01-15")) == "2026-12"
