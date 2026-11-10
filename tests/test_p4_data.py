import pandas as pd
import pytest

from quant.data import sources
from quant.data.sources import french_to_price, parse_french_csv

TEXT = """This file was created using the 202609 CRSP database.
Some description line

,SMALL LoPRIOR,BIG HiPRIOR
19630701,   0.10,   0.50
19630702,   0.20, -99.99

 Average Equal Weighted Returns -- Daily
,SMALL LoPRIOR,BIG HiPRIOR
19630701,   9.00,   9.00
"""


def test_parse_french_first_section_only():
    df = parse_french_csv(TEXT)
    assert len(df) == 2
    assert isinstance(df.index[0], pd.Timestamp)
    assert df["BIG HiPRIOR"].iloc[0] == pytest.approx(0.005)
    assert pd.isna(df["BIG HiPRIOR"].iloc[1])


def test_french_to_price():
    r = pd.Series([0.01, -0.02], pd.to_datetime(["2020-01-02", "2020-01-03"]))
    assert list(french_to_price(r)) == pytest.approx([1.01, 0.9898])


def test_csindex_drops_placeholder(monkeypatch):
    import akshare as ak
    df = pd.DataFrame({"日期": pd.to_datetime(["2000-01-01", "2005-12-30", "2006-01-04"]).date,
                       "收盘": [1000.0, 1000.0, 1010.0]})
    monkeypatch.setattr(ak, "stock_zh_index_hist_csindex", lambda **k: df)
    s = sources.fetch_csindex("H20269")
    assert s.index[0] == pd.Timestamp("2005-12-30")
    assert list(s) == [1000.0, 1010.0]
