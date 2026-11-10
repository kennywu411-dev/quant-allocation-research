import pandas as pd
import pytest

from quant.data import sources


def _fake():
    return pd.Series([10.0, 11.0], index=pd.to_datetime(["2024-01-02", "2024-01-03"]))


def test_fetch_cn_falls_back_to_baostock(monkeypatch):
    def ak_fail(code, start, kind, adjust="hfq"):
        raise RuntimeError("akshare changed")

    monkeypatch.setattr(sources, "_cn_akshare", ak_fail)
    monkeypatch.setattr(sources, "_cn_baostock", lambda code, start, kind, adjust="hfq": _fake())
    s = sources.fetch_cn("000651", "2024-01-01", "stock")
    assert s.attrs["source"] == "baostock"


def test_fetch_cn_error_names_code(monkeypatch):
    def fail(code, start, kind, adjust="hfq"):
        raise RuntimeError("down")

    monkeypatch.setattr(sources, "_cn_akshare", fail)
    monkeypatch.setattr(sources, "_cn_baostock", fail)
    with pytest.raises(sources.DataSourceError, match="000651"):
        sources.fetch_cn("000651", "2024-01-01", "stock")
