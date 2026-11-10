import numpy as np
import pandas as pd
import pytest

from quant.portfolio.checkup import fill_with_proxy, portfolio_nav, risk_contribution, stress_table


def _idx(n, start="2024-01-01"):
    return pd.date_range(start, periods=n, freq="B")


def test_fill_with_proxy_keeps_real_part():
    idx = _idx(100)
    proxy = pd.Series(np.linspace(100, 150, 100), index=idx)
    real = pd.Series(np.linspace(10, 20, 50), index=idx[50:])
    filled, cutoff = fill_with_proxy(real, proxy)
    pd.testing.assert_series_equal(filled.loc[idx[50]:], real, check_names=False, check_freq=False)
    assert filled.loc[idx[50]] / filled.loc[idx[49]] == pytest.approx(proxy.iloc[50] / proxy.iloc[49])
    assert cutoff == idx[50]
    _, none_cut = fill_with_proxy(proxy, proxy)
    assert none_cut is None


def test_portfolio_nav_cash_constant():
    h = pd.DataFrame({"symbol": ["CASH"], "shares": [100.0], "ccy": ["AUD"]})
    nav = portfolio_nav(h, pd.DataFrame(index=_idx(5)))
    assert nav.nunique() == 1


def test_risk_contribution_sums_to_one():
    r = pd.Series(np.random.default_rng(0).normal(0, 0.01, 300))
    rets = pd.DataFrame({"a": r, "b": r})
    rc = risk_contribution(pd.Series({"a": 0.5, "b": 0.5}), rets)
    assert rc.sum() == pytest.approx(1.0)
    assert rc["a"] == pytest.approx(0.5)


def test_stress_table_skips_missing_window():
    nav = pd.Series(np.linspace(100, 120, 800), index=_idx(800, "2019-01-01"))
    t = stress_table(nav)
    assert np.isnan(t.loc["2008 金融危机", "收益"])
    assert not np.isnan(t.loc["2022 加息熊市", "收益"])
