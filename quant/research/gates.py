"""设计文档第 6 节验证门槛（核心配置版本，不含 DSR）。"""
import numpy as np
import pandas as pd

from quant.metrics import cagr, max_drawdown

MDD_LIMIT = -0.15
PERIODS = {
    "2008 金融危机": ("2008-09-01", "2009-03-31"),
    "2015 股灾": ("2015-06-01", "2016-02-29"),
    "2018 全年": ("2018-01-01", "2018-12-31"),
    "2020 新冠": ("2020-02-15", "2020-03-31"),
    "2022 全年": ("2022-01-01", "2022-12-31"),
    "2024 年初": ("2024-01-01", "2024-02-29"),
}


def drop_best_year_cagr(nav: pd.Series) -> float:
    r = nav.pct_change().dropna()
    by_year = (1 + r).groupby(r.index.year).prod()
    rest = r[r.index.year != by_year.idxmax()]
    if rest.empty:
        return float("nan")
    days_per_year = len(r) / ((nav.index[-1] - nav.index[0]).days / 365.25)
    years = len(rest) / days_per_year
    return float(np.prod(1 + rest.values) ** (1 / years) - 1)


def period_returns(nav: pd.Series) -> dict[str, float]:
    out = {}
    for k, (a, b) in PERIODS.items():
        prev = nav.loc[:a].iloc[:-1] if pd.Timestamp(a) in nav.index else nav.loc[:a]
        seg = nav.loc[a:b]
        if len(prev) == 0 or len(seg) == 0:
            out[k] = float("nan")
        else:
            out[k] = float(seg.iloc[-1] / prev.iloc[-1] - 1)
    return out


def evaluate(navs_aud_by_mode: dict[str, pd.Series], nav_cost2: pd.Series, split: str = "2019-12-31",
             baseline: pd.Series | None = None) -> dict:
    end = navs_aud_by_mode["end"]
    is_nav, oos_nav = end.loc[:split], end.loc[split:]
    r = {
        "is_cagr": cagr(is_nav),
        "oos_cagr": cagr(oos_nav),
        "full_cagr": cagr(end),
        "full_mdd": max_drawdown(end),
        "mdd_worst": min(max_drawdown(n) for n in navs_aud_by_mode.values()),
        "cagr_spread": max(cagr(n) for n in navs_aud_by_mode.values()) - min(cagr(n) for n in navs_aud_by_mode.values()),
        "cost2_cagr": cagr(nav_cost2),
        "drop_best_cagr": drop_best_year_cagr(end),
    }
    r["g_oos"] = bool(r["oos_cagr"] > 0 and r["oos_cagr"] >= 0.5 * r["is_cagr"])
    r["g_cost2"] = bool(r["cost2_cagr"] > 0)
    r["g_mdd"] = bool(r["mdd_worst"] >= MDD_LIMIT)
    r["spread_ok"] = bool(r["cagr_spread"] <= 0.02)
    r["g_rebal"] = bool(r["spread_ok"] and r["g_mdd"])
    r["g_period"] = bool(r["drop_best_cagr"] > 0)
    r["g_vs_base"] = None
    if baseline is not None:
        b = baseline.loc[end.index[0]:]
        r["base_mdd"], r["base_cagr"] = max_drawdown(b), cagr(b)
        r["g_vs_base"] = bool(r["full_mdd"] - r["base_mdd"] >= 0.03 and r["base_cagr"] - r["full_cagr"] <= 0.02)
    gates = [r["g_oos"], r["g_cost2"], r["g_mdd"], r["g_rebal"], r["g_period"]]
    if r["g_vs_base"] is not None:
        gates.append(r["g_vs_base"])
    r["passed"] = all(gates)
    return r
