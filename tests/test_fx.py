import pytest
import numpy as np
import pandas as pd

from quant.fx import align, to_aud


def _s(vals, dates):
    return pd.Series(vals, index=pd.to_datetime(dates), dtype=float)


def test_to_aud_usd():
    p = _s([100, 110], ["2024-01-02", "2024-01-03"])
    fx = {"AUDUSD": _s([0.5, 0.55], ["2024-01-02", "2024-01-03"])}
    assert to_aud(p, "USD", fx).tolist() == pytest.approx([200.0, 200.0])


def test_to_aud_no_lookahead():
    p = _s([100, 100, 100], ["2024-01-02", "2024-01-03", "2024-01-04"])
    fx = {"AUDUSD": _s([0.5, 1.0], ["2024-01-02", "2024-01-04"])}
    out = to_aud(p, "USD", fx)
    assert out.loc["2024-01-03"] == 200.0  # 用第 1 天的汇率，而不是第 3 天的


def test_align_keeps_holiday_rows():
    us = _s([1, 2, 3, 4], ["2024-02-08", "2024-02-09", "2024-02-12", "2024-02-13"])
    cn = _s([10, 11], ["2024-02-08", "2024-02-19"])  # 春节休市
    df = align({"US": us, "CN": cn})
    assert len(df) == 5
    assert df.loc["2024-02-12", "CN"] == 10


def test_align_nan_before_first_valid():
    a = _s([1, 2], ["2024-01-01", "2024-01-02"])
    b = _s([5], ["2024-01-02"])
    df = align({"a": a, "b": b})
    assert np.isnan(df.loc["2024-01-01", "b"])


def test_to_base_cny():
    from quant.fx import to_base
    idx = pd.to_datetime(["2020-01-02", "2020-01-03"])
    fx = {"AUDUSD": pd.Series([0.5, 0.5], idx), "AUDCNY": pd.Series([4.0, 5.0], idx)}
    usd = pd.Series([10.0, 10.0], idx)
    # 1 美元 = AUDCNY/AUDUSD 人民币
    assert list(to_base(usd, "USD", fx, "CNY")) == pytest.approx([80.0, 100.0])
    cny = pd.Series([7.0, 8.0], idx)
    assert list(to_base(cny, "CNY", fx, "CNY")) == [7.0, 8.0]
    assert list(to_base(cny, "CNY", fx, "AUD")) == pytest.approx([1.75, 1.6])


def test_p3_uses_cny_base():
    from quant.research import p3
    assert p3.BASE == "CNY"
