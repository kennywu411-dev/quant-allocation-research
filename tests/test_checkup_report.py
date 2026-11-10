import subprocess
import sys
from datetime import date

import numpy as np
import pandas as pd

from quant.report.checkup_report import SECTIONS, render


def _inputs(proxy_notes):
    idx = pd.date_range("2019-01-01", periods=500, freq="B")
    nav = pd.Series(np.linspace(100, 90, 500), index=idx)
    h = pd.DataFrame({"account": ["a"], "market": ["US"], "symbol": ["AAPL"], "shares": [7.0], "ccy": ["USD"]})
    vals = pd.Series({"AAPL": 1000.0})
    rc = pd.Series({"AAPL": 1.0})
    corr = pd.DataFrame([[1.0]], index=["AAPL"], columns=["AAPL"])
    from quant.metrics import worst_drawdowns
    from quant.portfolio.checkup import stress_table
    return dict(h=h, nav=nav, values_aud=vals, risk_contrib=rc, corr=corr, stress=stress_table(nav),
                worst=worst_drawdowns(nav), proxy_notes=proxy_notes, as_of=date(2026, 10, 30))


def test_report_has_disclaimer_and_sections():
    md = render(**_inputs([]))
    assert "不是投资建议" in md
    for s in SECTIONS:
        assert s in md
    assert len(SECTIONS) == 8


def test_report_mentions_proxy():
    md = render(**_inputs(["NVDA：2026-06-12 之前用 QQQ 收益补齐，可信度低"]))
    assert "NVDA" in md and "可信度低" in md


def test_report_no_advice_words():
    md = render(**_inputs([]))
    assert "建议卖出" not in md and "建议买入" not in md


def test_cli_exits_when_shares_missing(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("account,market,symbol,shares,ccy,cost_basis,buy_date\na,US,AAPL,,USD,,\n")
    r = subprocess.run([sys.executable, "-m", "quant.checkup", "--holdings", str(p)],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "请填写股数" in (r.stdout + r.stderr)


def test_report_flags_estimates_and_data_dates():
    inp = _inputs([])
    info = pd.DataFrame({"最后日期": ["2026-10-29"], "来源": ["yfinance"], "抓取时间": ["2026-10-30T20:59"],
                         "旧缓存": [True]}, index=["AAPL"])
    md = render(**inp, estimates=["CASH（USD）：估算值"], data_info=info, nav_ref=inp["nav"])
    assert "估算值" in md
    assert "2026-10-29" in md
    assert "旧缓存" in md


def test_report_warns_hindsight_bias_on_return():
    md = render(**_inputs([]))
    assert "后视偏差" in md
