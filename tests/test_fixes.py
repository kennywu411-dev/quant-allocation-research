import numpy as np
import pandas as pd
import pytest

from quant.data.cache import load_or_fetch
from quant.data.sources import clean_spikes
from quant.portfolio.checkup import cash_price_aud, fill_with_proxy, weighted_nav, weekly_returns


def _idx(n, start="2024-01-01"):
    return pd.date_range(start, periods=n, freq="B")


def test_weighted_nav_keeps_today_weights():
    # C1：股票 50%、现金 50%，股票跌 50% → 按当前权重回放应跌 25%，不被早年现金占比稀释
    idx = _idx(3)
    prices = pd.DataFrame({"A": [100.0, 50.0, 50.0], "CASH": [1.0, 1.0, 1.0]}, index=idx)
    nav = weighted_nav(pd.Series({"A": 0.5, "CASH": 0.5}), prices)
    assert nav.iloc[1] / nav.iloc[0] - 1 == pytest.approx(-0.25)


def test_cash_price_aud_carries_fx_risk():
    # I1：美元现金按 1/AUDUSD 计价
    fx = {"AUDUSD": pd.Series([0.5, 0.8], index=_idx(2))}
    s = cash_price_aud("USD", fx, _idx(2))
    assert s.tolist() == pytest.approx([2.0, 1.25])


def test_proxy_is_vol_scaled():
    # I2：代理收益按真实段波动缩放
    idx = _idx(200)
    rng = np.random.default_rng(1)
    proxy = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, 200)), index=idx)
    real_r = rng.normal(0, 0.04, 100)
    real = pd.Series(10 * np.cumprod(1 + real_r), index=idx[100:])
    filled, _ = fill_with_proxy(real, proxy, vol_scale=True)
    early = filled.loc[:idx[99]].pct_change().dropna().std()
    assert early > 0.025


def test_clean_spikes_removes_one_day_fx_glitch():
    # I3：6.90 → 6.24 → 6.83 这种一日尖刺要被抹平
    s = pd.Series([6.90, 6.24, 6.83, 6.85], index=_idx(4))
    out = clean_spikes(s, threshold=0.05)
    assert out.iloc[1] == pytest.approx(6.90)
    assert out.iloc[3] == 6.85


def test_weekly_returns_used_for_correlation():
    # I4：周收益（W-FRI）
    prices = pd.DataFrame({"A": np.linspace(1, 2, 20)}, index=_idx(20))
    w = weekly_returns(prices)
    assert all(d.weekday() == 4 for d in w.index)


def test_cache_marks_stale_and_fetched_at(tmp_path):
    # I5：用了旧缓存要能在报告里看出来
    import json
    s = pd.Series([1.0], index=pd.to_datetime(["2024-01-02"]))
    s.attrs["source"] = "fake"
    load_or_fetch("X", lambda: s, cache_dir=tmp_path)
    m = json.loads((tmp_path / "X.meta.json").read_text())
    m["fetched_at"] = "2000-01-01T00:00:00"
    (tmp_path / "X.meta.json").write_text(json.dumps(m))

    def boom():
        raise RuntimeError("429")

    with pytest.warns(UserWarning):
        out = load_or_fetch("X", boom, cache_dir=tmp_path)
    assert out.attrs["stale"] is True
    assert out.attrs["fetched_at"].startswith("2000")


def test_latest_quote_scaling_uses_same_date(monkeypatch):
    # I6：缩放用两个序列共有的日期
    from quant.data import update
    raw = pd.Series([80.0], index=pd.to_datetime(["2026-10-29"]))
    raw.attrs["source"] = "fake"
    monkeypatch.setattr(update, "load_or_fetch", lambda key, fetch, **kw: raw)
    d, p = update.latest_quote("000651", "CN", "stock")
    assert d == pd.Timestamp("2026-10-29") and p == 80.0
