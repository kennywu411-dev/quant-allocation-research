import pandas as pd
import pytest

from quant.data.update import fix_splits


def test_split_jump_removed():
    i = pd.bdate_range("2025-01-06", periods=6)
    s = pd.Series([2.2, 2.255, 2.26, 0.85, 0.86, 0.87], index=i)   # 第 4 天份额拆分
    out, events = fix_splits(s, 0.30)
    r = out.pct_change().dropna()
    assert r.iloc[2] == pytest.approx(0.0)
    assert r.iloc[0] == pytest.approx(2.255 / 2.2 - 1)          # 拆分前的真实收益不变
    assert out.iloc[-1] == 0.87                                  # 最新价保持实际价
    assert [d for d, _ in events] == [i[3]]


def test_normal_limit_move_kept():
    i = pd.bdate_range("2025-01-06", periods=3)
    s = pd.Series([1.0, 1.2, 1.0], index=i)                      # 创业板 ETF 涨跌停 ±20% 属于正常
    out, events = fix_splits(s, 0.30)
    assert events == [] and list(out) == [1.0, 1.2, 1.0]


def test_split_events_recorded(monkeypatch):
    import quant.data.update as u
    i = pd.bdate_range("2025-01-06", periods=4)
    monkeypatch.setattr(u, "load_or_fetch", lambda key, fn: pd.Series([2.2, 2.26, 0.85, 0.86], index=i))
    u.SPLIT_LOG.clear()
    u.get_price("512100", "CN", "etf")
    assert "512100" in u.SPLIT_LOG and u.SPLIT_LOG["512100"][0][0] == i[2]
    assert any("512100" in n for n in u.split_notes())
