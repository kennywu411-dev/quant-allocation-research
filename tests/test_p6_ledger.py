import pandas as pd
import pytest

from quant.live.ledger import (alert_level, drawdown, flows_between, portfolio_value_cny, record, should_record)

D = pd.Timestamp


def _ledger():
    led = record(None, D("2026-11-02"), 100.0, 0.0)
    led = record(led, D("2026-11-03"), 150.0, 50.0)
    return led


def test_flow_does_not_change_nav():
    led = _ledger()
    assert led.nav.iloc[-1] == pytest.approx(1.0)
    assert led.units.iloc[-1] == pytest.approx(150.0)


def test_loss_after_flow():
    led = record(_ledger(), D("2026-11-04"), 135.0, 0.0)
    assert led.nav.iloc[-1] == pytest.approx(0.9)
    assert drawdown(led) == pytest.approx(-0.10)


def test_same_day_replaces():
    led = record(_ledger(), D("2026-11-03"), 140.0, 50.0)
    assert len(led) == 2
    assert led.value_cny.iloc[-1] == 140.0
    assert led.units.iloc[-1] == pytest.approx(150.0)


def test_alert_levels():
    # 2026-11-06 换成激进版（-50%）：上限 -50%（用户决定），-15% 仍只提醒复盘（用户 2026-10-31 决定）
    assert alert_level(-0.149) == "正常"
    assert alert_level(-0.15) == "复盘提醒"
    assert alert_level(-0.49) == "复盘提醒"
    assert alert_level(-0.50) == "触及上限"


def test_stale_price_not_recorded():
    assert should_record(D("2026-10-30"), D("2026-11-02"))
    assert not should_record(D("2026-10-20"), D("2026-11-02"))


def test_value_and_flows_in_cny():
    h = pd.DataFrame([{"account": "moomoo", "symbol": "SPY", "shares": 2, "ccy": "USD"},
                      {"account": "moomoo", "symbol": "CASH", "shares": 100, "ccy": "USD"},
                      {"account": "银河", "symbol": "510300", "shares": 100, "ccy": "CNY"}])
    quotes = {"SPY": (D("2026-10-30"), 50.0), "510300": (D("2026-10-29"), 4.0)}
    fx = {"USD": 0.5, "CNY": 3.5, "AUD": 1.0}  # 1 澳元 = 0.5 美元 = 3.5 元 → 1 美元 = 7 元
    v, pdate = portfolio_value_cny(h, quotes, fx)
    assert v == pytest.approx(200 * 7 + 400)
    assert pdate == D("2026-10-29")
    flows = pd.DataFrame([{"date": "2026-11-03", "account": "moomoo", "amount": 10, "ccy": "USD", "note": ""},
                          {"date": "2026-11-01", "account": "银河", "amount": 5, "ccy": "CNY", "note": ""}])
    assert flows_between(flows, D("2026-11-02"), D("2026-11-03"), fx) == pytest.approx(70.0)
    assert flows_between(flows, None, D("2026-11-03"), fx) == pytest.approx(75.0)


def test_late_entered_flow_still_booked():
    from quant.live.ledger import pending_flows
    fx = {"USD": 0.5, "CNY": 3.5, "AUD": 1.0}
    flows = pd.DataFrame([{"date": "2026-11-03", "account": "moomoo", "amount": 10, "ccy": "USD", "note": ""}])
    # 11-03 那行已在 9:00 记完（当时 flows 还没有这笔），之后才补录日期为 11-03 的入金
    totals, flow_cny = pending_flows(flows, {"USD": 0.0, "CNY": 0.0, "AUD": 0.0}, D("2026-11-04"), fx)
    assert flow_cny == pytest.approx(70.0)
    assert totals["USD"] == 10
    _, again = pending_flows(flows, totals, D("2026-11-05"), fx)
    assert again == 0


def test_old_ledger_without_booked_columns():
    from quant.live.ledger import booked_of
    old = pd.DataFrame([{"date": D("2026-10-31"), "value_cny": 100.0, "flow_cny": 0.0, "units": 100.0, "nav": 1.0,
                         "price_date": D("2026-10-29")}])
    old["booked_USD"] = float("nan")
    assert booked_of(old, D("2026-11-02")) == {"USD": 0.0, "CNY": 0.0, "AUD": 0.0}
