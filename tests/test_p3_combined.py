import numpy as np
import pandas as pd
import pytest

from quant.research.p3 import combine_navs, select_pair


def _nav(vals, start="2015-01-01"):
    return pd.Series(vals, index=pd.date_range(start, periods=len(vals), freq="B"), dtype=float)


def test_combine_navs_weights_and_window():
    us = _nav([100, 50, 100, 100], "2015-01-01")
    cn = _nav([10, 10, 10], "2015-01-02")
    c = combine_navs(us, cn, 0.5)
    assert c.index[0] == pd.Timestamp("2015-01-02")
    assert c.iloc[0] == pytest.approx(1.0)
    assert c.iloc[1] == pytest.approx(0.5 * 2 + 0.5)  # 美股从 50 涨回 100


def _acct(names, cagr_is):
    return pd.DataFrame({"name": names, "is_cagr": cagr_is, "eligible": True})


def test_select_pair_respects_combined_mdd():
    idx_vals = np.linspace(100, 200, 600)
    good = _nav(idx_vals)
    crash = good.copy()
    crash.iloc[300:] *= 0.5
    us = _acct(["u_good", "u_crash"], [0.05, 0.20])
    cn = _acct(["c1"], [0.05])
    navs_us = {"u_good": {m: good for m in ("end", "mid", "start")},
               "u_crash": {m: crash for m in ("end", "mid", "start")}}
    navs_cn = {"c1": {m: good for m in ("end", "mid", "start")}}
    pick, table = select_pair(us, cn, navs_us, navs_cn, w_us=0.5, split="2015-06-30")
    assert pick == ("u_good", "c1")
    assert len(table) == 2


def test_select_pair_none_when_all_fail():
    good = _nav(np.linspace(100, 200, 600))
    crash = good.copy()
    crash.iloc[300:] *= 0.5
    us = _acct(["u"], [0.1])
    cn = _acct(["c"], [0.1])
    navs = {m: crash for m in ("end", "mid", "start")}
    pick, _ = select_pair(us, cn, {"u": navs}, {"c": navs}, w_us=0.5, split="2015-06-30")
    assert pick is None
