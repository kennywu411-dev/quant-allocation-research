"""P5 最终方案的基准对比（口径与 P5 报告一致：两账户合并、人民币计、2007-06-01 至 2026-10-30、同样的成本与账户权重，
最大回撤取月初 / 月中 / 月末三种调仓日中最差的）。
- P5：基础权重 + 10 个月均线转国债（复现报告数字，用来确认口径）；
- 基准 1：同样的基础权重、不加均线，只做月度再平衡（static）；
- 基准 2：纯股票，美股账户 100% SPY、A股账户 100% 沪深300 ETF（510300，上市前用指数补齐），月度再平衡。
另给 2008、2015、2018、2022 年的当年收益和年内最大回撤（月末调仓口径）。
python -m quant.research.benchmarks → research/p5_benchmarks.json"""
import json
from pathlib import Path

import pandas as pd

OUT = Path("research/p5_benchmarks.json")
YEARS = [2008, 2015, 2018, 2022]
PURE = {"美股账户": {"SPY": 1.0}, "A股账户": {"510300": 1.0}}


def year_stats(nav: pd.Series, years: list[int] = YEARS) -> dict:
    """每个年份：当年收益（上年末到当年末；起始年用第一天）和年内最大回撤（从年内高点算）。"""
    from quant.metrics import max_drawdown
    out = {}
    for y in years:
        cur = nav[nav.index.year == y]
        if cur.empty:
            continue
        prev = nav[nav.index.year < y]
        start = prev.iloc[-1] if len(prev) else cur.iloc[0]
        out[str(y)] = {"ret": float(cur.iloc[-1] / start - 1), "mdd": float(max_drawdown(pd.concat([prev.iloc[-1:], cur])))}
    return out


def _combs(variant: str, get_price, get_index, fx, end: str, w_us: float) -> dict[str, pd.Series]:
    from quant.backtest.strategies import rebalance_dates
    from quant.research import p3
    from quant.research.p4 import CORE
    navs = {}
    for label, (e, split, signal) in CORE.items():
        a = p3.ACCOUNTS[label]
        px = p3.build_prices(a, get_price, get_index, fx)[0].loc[:end]
        base = PURE[label] if variant == "pure" else p3._base_weights(a, e, p3.SPLITS[split])
        sig = signal if variant == "p5" else "static"
        navs[label] = p3.run_trial(px, base, sig, a, fx, rebalance_dates(px, "end")[12])[0]
    return {m: p3.combine_navs(navs["美股账户"][m], navs["A股账户"][m], w_us) for m in ("end", "mid", "start")}


def main() -> int:
    import warnings
    warnings.filterwarnings("ignore")
    from quant.data.update import get_csindex, get_index, get_price
    from quant.research.resume_metrics import P5_PARAMS, p5_w_us, summarize
    fx = {"AUDUSD": get_price("AUDUSD", "FX", "fx"), "AUDCNY": get_price("AUDCNY", "FX", "fx")}
    rf = get_csindex("H11025")
    w_us = p5_w_us()
    out = {"口径": "两账户合并、人民币计、与 P5 报告相同的成本和账户权重；最大回撤取三种调仓日最差；分年数字为月末调仓口径",
           "report": P5_PARAMS["report"]}
    labels = {"p5": "P5（基础权重 + 10 个月均线）", "static": "基准1：同权重不加均线", "pure": "基准2：纯股票（SPY / 沪深300）"}
    for v, name in labels.items():
        c = _combs(v, get_price, get_index, fx, P5_PARAMS["end"], w_us)
        out[name] = {**summarize(c, rf), "years": year_stats(c["end"])}
        s = out[name]
        print(f"{name}：全期 {s['full_cagr']:.2%}，样本外 {s['oos_cagr']:.2%}，最差回撤 {s['mdd_worst']:.2%}，"
              f"波动 {s['ann_vol']:.2%}，夏普 {s['sharpe']:.2f}；" +
              "，".join(f"{y} {d['ret']:+.1%}/{d['mdd']:.1%}" for y, d in s["years"].items()))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
