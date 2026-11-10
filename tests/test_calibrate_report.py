import pytest
from datetime import date

import pandas as pd

from quant.backtest.calibrate import SECTION_TITLES, render, summary


def test_report_sections_and_disclaimer():
    df = pd.DataFrame({"CAGR": [0.1]}, index=["x"])
    md = render({t: df for t in SECTION_TITLES}, date(2026, 10, 30))
    assert "不是投资建议" in md
    assert len(SECTION_TITLES) == 4
    for t in SECTION_TITLES:
        assert t in md


def test_summary_keys():
    nav = pd.Series([100.0, 110.0, 99.0, 120.0], index=pd.date_range("2024-01-01", periods=4, freq="D"))
    s = summary(nav)
    assert set(s) == {"CAGR", "最大回撤", "年化波动", "夏普"}
    assert s["最大回撤"] == pytest.approx(-0.1)


def test_cost_column_is_money_not_percent():
    df = pd.DataFrame({"CAGR": [0.1], "成本合计": [0.0]}, index=["x"])
    md = render({t: df for t in SECTION_TITLES}, date(2026, 10, 30))
    assert "| 10.00% | 0 |" in md


def test_rules_note_says_not_triggered():
    from quant.backtest.calibrate import rules_note
    assert "没触发" in rules_note(0)
    assert "3" in rules_note(3)


def test_blocked_column_is_count():
    df = pd.DataFrame({"CAGR": [0.1], "被挡订单": [0.0]}, index=["x"])
    md = render({t: df for t in SECTION_TITLES}, date(2026, 10, 30))
    assert "| 10.00% | 0 |" in md
