import numpy as np
import pandas as pd
import pytest

from quant.research.mom_stocks import bias_report, momentum_rank, top_n_portfolio

IDX = pd.bdate_range("2020-01-01", periods=300)


def test_momentum_skips_last_month():
    flat_then_jump = np.r_[np.full(279, 100.0), np.linspace(100, 200, 21)]
    steady = np.linspace(100, 130, 300)
    px = pd.DataFrame({"JUMP": flat_then_jump, "STEADY": steady}, index=IDX)
    r = momentum_rank(px, IDX[-1])
    assert list(r.index) == ["STEADY", "JUMP"]


def test_top_n_equal_weight():
    rng = np.random.default_rng(1)
    px = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0.0005, 0.01, (300, 8)), axis=0), index=IDX,
                      columns=list("ABCDEFGH"))
    dates = pd.DatetimeIndex([IDX[260], IDX[280], IDX[299]])
    w = top_n_portfolio(px, 3, dates)
    assert (w.sum(axis=1).round(10) == 1).all()
    assert ((w > 0).sum(axis=1) == 3).all()
    assert set(np.round(w.values[w.values > 0], 10)) == {round(1 / 3, 10)}


def test_bias_report_sign():
    i = pd.bdate_range("2015-01-01", periods=505)
    real = pd.Series(1.12 ** (np.arange(505) / 252), index=i)
    french = pd.Series(1.08 ** (np.arange(505) / 252), index=i)
    b = bias_report(real, french)
    assert b["bias"] == pytest.approx(0.04, abs=1e-6)
