import pandas as pd
import pytest

from quant.research import p3
from quant.research.aggr_data import leveraged, tracking_error

D = pd.bdate_range("2026-01-05", periods=5)


def test_leveraged_daily_compounding():
    base = pd.Series([100.0, 110.0, 99.0], index=D[:3])
    out = leveraged(base, 2, 0.0, pd.Series(0.0, index=D[:3]))
    assert list(out.round(10)) == [1.0, 1.2, 0.96]


def test_leveraged_costs():
    base = pd.Series(100.0, index=D)
    out = leveraged(base, 2, 0.0095, pd.Series(0.0001, index=D))
    r = out.pct_change().dropna()
    assert r.iloc[0] == pytest.approx(-(0.0095 / 252 + 0.0001))


def _fail_get_price(s, market, kind):
    if s == "MOMBIG":
        raise AssertionError("纯代理资产不该调用 get_price")
    return pd.Series([1.0, 1.0, 1.0, 1.0, 1.0], index=D, name=s)


def test_synthetic_asset_not_fetched():
    a = dict(market="US", eq=["MOMBIG"], bond=["IEF"], gold=[], synthetic={"MOMBIG": ("french", "x:y", 0.01)})
    getters = {"french": lambda code: pd.Series(1.0, index=D)}
    px, notes = p3.build_prices(a, _fail_get_price, None, {}, getters)
    assert "MOMBIG" in px
    assert px.MOMBIG.pct_change().iloc[1] == pytest.approx(-0.01 / 252)
    assert any("MOMBIG" in n for n in notes)


def test_lev_proxy_fills_before_inception():
    spy = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0], index=D)
    sso = pd.Series([50.0, 51.0, 52.0], index=D[2:])
    gp = lambda s, m, k: {"SPY": spy, "SSO": sso}[s]  # noqa: E731
    a = dict(market="US", eq=["SSO"], bond=[], gold=[], proxy={"SSO": ("lev", "SPY")})
    getters = {"lev": lambda code: leveraged(gp(code, "US", "etf"), 2, 0.0, pd.Series(0.0, index=D))}
    px, _ = p3.build_prices(a, gp, None, {}, getters)
    assert px.index[0] == D[0]
    assert px.SSO.loc[D[2]] == 50.0
    assert px.SSO.loc[D[1]] / px.SSO.loc[D[0]] - 1 == pytest.approx(0.02)


def test_tracking_error():
    i = pd.bdate_range("2020-01-01", periods=253)
    real = pd.Series(1.10 ** (pd.RangeIndex(253) / 252), index=i)
    synth = pd.Series(1.08 ** (pd.RangeIndex(253) / 252), index=i)
    assert tracking_error(real, synth) == pytest.approx(0.02, abs=1e-6)
