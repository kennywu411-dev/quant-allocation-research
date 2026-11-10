import pandas as pd

from quant.research.benchmarks import year_stats


def test_year_stats_return_and_intra_year_drawdown():
    idx = pd.to_datetime(["2007-12-31", "2008-03-31", "2008-06-30", "2008-12-31", "2009-12-31"])
    nav = pd.Series([100.0, 110.0, 66.0, 88.0, 100.0], index=idx)
    s = year_stats(nav, [2008, 2015])
    assert abs(s["2008"]["ret"] - (-0.12)) < 1e-12
    assert abs(s["2008"]["mdd"] - (66 / 110 - 1)) < 1e-12
    assert "2015" not in s
