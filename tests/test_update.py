import pandas as pd

from quant.data import update


UNI = "symbol,market,kind,ccy,name\nAAPL,US,stock,USD,苹果\n000651,CN,stock,CNY,格力电器\n510300,CN,etf,CNY,沪深300ETF\n"


def _uni(tmp_path, monkeypatch):
    p = tmp_path / "universe.csv"
    p.write_text(UNI)
    monkeypatch.setattr(update, "UNIVERSE_PATH", p)
    monkeypatch.setattr(update.load_universe, "__defaults__", (p,))
    return p


def test_load_universe_keeps_leading_zeros(tmp_path, monkeypatch):
    u = update.load_universe(_uni(tmp_path, monkeypatch))
    assert "000651" in u["symbol"].tolist()


def test_update_all_continues_on_error(tmp_path, monkeypatch):
    _uni(tmp_path, monkeypatch)
    def fake(symbol, market, kind, start="2005-01-01"):
        if symbol == "AAPL":
            raise RuntimeError("boom")
        s = pd.Series([1.0], index=pd.to_datetime(["2024-01-02"]), name=symbol)
        s.attrs["source"] = "fake"
        return s

    monkeypatch.setattr(update, "get_price", fake)
    out = update.update_all()
    assert len(out) == len(update.load_universe())
    assert out.set_index("symbol").loc["AAPL", "error"]


def test_latest_price_cn_uses_unadjusted(monkeypatch):
    seen = {}

    def fake_fetch_cn(code, start, kind, adjust="hfq"):
        seen["adjust"] = adjust
        s = pd.Series([42.0], index=pd.to_datetime(["2026-10-30"]))
        s.attrs["source"] = "fake"
        return s

    monkeypatch.setattr(update, "fetch_cn", fake_fetch_cn)
    monkeypatch.setattr(update, "load_or_fetch", lambda key, fetch, **kw: fetch())
    assert update.latest_price("000651", "CN", "stock") == 42.0
    assert seen["adjust"] == ""
