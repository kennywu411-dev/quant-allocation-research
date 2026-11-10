import numpy as np
import pandas as pd

from quant.backtest import costs
from quant.backtest.crosscheck import run_bt
from quant.backtest.engine import run_backtest
from quant.backtest.strategies import month_ends


def test_crosscheck_matches_engine_on_synthetic():
    rng = np.random.default_rng(7)
    idx = pd.date_range("2020-01-01", periods=500, freq="B")
    px = pd.DataFrame({"A": 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, 500)),
                       "B": 50 * np.cumprod(1 + rng.normal(0.0002, 0.005, 500))}, index=idx)
    me = month_ends(px)
    w = pd.DataFrame({"A": [1.0 if i % 2 else 0.3 for i in range(len(me))],
                      "B": [0.0 if i % 2 else 0.7 for i in range(len(me))]}, index=me)
    ours = run_backtest(px, w, {"A": costs.zero(), "B": costs.zero()}, fractional=True).nav
    theirs = run_bt(px, w)
    start = ours.index[ours.index > me[0]][0]
    r_ours = ours.iloc[-1] / ours.loc[start]
    r_bt = theirs.iloc[-1] / theirs.loc[start]
    assert abs(r_ours / r_bt - 1) < 1e-4
