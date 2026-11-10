import pandas as pd
import pytest

from quant.research.gates import PERIODS, evaluate
from quant.research.p3 import EQUITY, account_values, align_modes, margin_note
from quant.research.registry import new_run_id


def test_equity_grid_goes_down_to_zero():
    # 规格 6.1：退回静态时把股票占比降到满足约束为止
    assert EQUITY[0] == 0.0 and 0.1 in EQUITY and 0.2 in EQUITY


def test_account_values_split_by_market():
    h = pd.DataFrame({"symbol": ["SPY", "000651", "CASH"], "market": ["US", "CN", "US"], "ccy": ["USD", "CNY", "USD"]})
    vals = pd.Series({"SPY": 100.0, "000651": 50.0, "CASH_USD": 10.0})
    assert account_values(h, vals) == (110.0, 50.0)


def test_align_modes_same_start():
    a = pd.Series(1.0, index=pd.date_range("2020-01-01", periods=10))
    b = pd.Series(1.0, index=pd.date_range("2020-01-03", periods=8))
    out = align_modes({"end": b, "mid": a, "start": a})
    assert all(s.index[0] == b.index[0] for s in out.values())


def test_rebal_spread_flag_independent_of_mdd():
    import numpy as np
    idx = pd.date_range("2012-01-02", periods=3000, freq="B")
    nav = pd.Series(100 * np.cumprod(np.full(3000, 1.0003)), index=idx)
    nav.iloc[1500:] *= 0.8
    r = evaluate({"end": nav, "mid": nav, "start": nav}, nav)
    assert r["g_mdd"] is False and r["spread_ok"] is True


def test_periods_include_2008():
    assert "2008 金融危机" in PERIODS


def test_margin_note_warns_when_close():
    assert "余量很小" in margin_note(-0.144)
    assert margin_note(-0.05) == ""


def test_run_id_format():
    rid = new_run_id()
    assert len(rid) > 10 and "_" in rid
