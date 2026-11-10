import numpy as np
import pandas as pd
import pytest

from quant.research.gates import drop_best_year_cagr, evaluate
from quant.research.registry import log_trial


def _yearly_nav(rets_by_year):
    parts, level = [], 100.0
    for y, r in rets_by_year.items():
        idx = pd.date_range(f"{y}-01-01", f"{y}-12-31", freq="B")
        daily = (1 + r) ** (1 / len(idx)) - 1
        vals = level * np.cumprod(np.full(len(idx), 1 + daily))
        level = vals[-1]
        parts.append(pd.Series(vals, index=idx))
    return pd.concat(parts)


def test_drop_best_year():
    nav = _yearly_nav({2020: 0.5, 2021: 0.0, 2022: 0.10})
    assert drop_best_year_cagr(nav) == pytest.approx(1.10 ** 0.5 - 1, rel=0.02)


def _steady(n=3000, mu=0.0003):
    idx = pd.date_range("2012-01-02", periods=n, freq="B")
    return pd.Series(100 * np.cumprod(np.full(n, 1 + mu)), index=idx)


def test_evaluate_fails_on_mdd():
    good = _steady()
    bad = good.copy()
    bad.iloc[1500:] *= 0.8
    r = evaluate({"end": good, "mid": bad, "start": good}, good)
    assert r["g_mdd"] is False and r["passed"] is False


def test_evaluate_vs_baseline():
    nav = _steady()
    nav.iloc[1500:] *= 0.9  # 回撤 -10%
    base = _steady()
    base.iloc[1500:] *= 0.89  # 回撤 -11%，只差 1 个百分点
    r = evaluate({"end": nav, "mid": nav, "start": nav}, nav, baseline=base)
    assert r["g_vs_base"] is False


def test_registry_appends(tmp_path):
    p = tmp_path / "t.csv"
    log_trial({"name": "a", "x": 1}, p)
    log_trial({"name": "b", "y": 2}, p)
    df = pd.read_csv(p)
    assert len(df) == 2 and df["logged_at"].notna().all() and "y" in df
