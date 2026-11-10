import numpy as np
import pandas as pd
import pytest

from quant.data import sources
from quant.research.p3 import build_prices, gold_cny


def _s(vals, start):
    return pd.Series(vals, index=pd.date_range(start, periods=len(vals), freq="B"), dtype=float)


def test_gold_cny_converts_usd_to_cny():
    gld = _s([100, 110], "2010-01-01")
    fx = {"AUDUSD": _s([0.5, 0.5], "2010-01-01"), "AUDCNY": _s([3.0, 3.0], "2010-01-01")}
    # 1 USD = AUDCNY/AUDUSD = 6 CNY
    assert gold_cny(gld, fx).tolist() == pytest.approx([600.0, 660.0])


def test_fetch_cn_index_error_names_code(monkeypatch):
    def fail(code, start):
        raise RuntimeError("down")
    monkeypatch.setattr(sources, "_idx_akshare", fail)
    monkeypatch.setattr(sources, "_idx_baostock", fail)
    with pytest.raises(sources.DataSourceError, match="sh000300"):
        sources.fetch_cn_index("sh000300", "2005-01-01")


def test_build_prices_splices_proxy_before_listing():
    etf = _s(np.linspace(10, 20, 50), "2012-03-01")
    idx = _s(np.linspace(1000, 3000, 200), "2011-08-01")
    a = {"eq": ["E"], "bond": [], "gold": [], "market": "CN", "proxy": {"E": ("index", "IDX")}}
    px, notes = build_prices(a, get_price=lambda s, m, k: etf, get_index=lambda c: idx, fx={})
    assert px["E"].first_valid_index() == idx.index[0]
    assert px["E"].loc[etf.index[0]:].tolist() == pytest.approx(etf.tolist())
    assert notes and "E" in notes[0] and "IDX" in notes[0]
