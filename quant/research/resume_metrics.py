"""补算面试常问的风险收益指标（年化波动、夏普、卡玛）：按报告当时的参数重建合并净值，先核对能复现报告里的年化和回撤，再算新指标。
python -m quant.research.resume_metrics  → research/resume_metrics.json"""
import json
from pathlib import Path

import pandas as pd

OUT = Path("research/resume_metrics.json")
# 报告当时的参数：P5（reports/P5-最终方案-2026-10-31.md，trials.csv 里 P5核心合并 的 w_us）；激进版（research/aggr_pick.json）
P5_PARAMS = {"end": "2026-10-30", "report": "reports/P5-最终方案-2026-10-31.md"}


def p5_w_us(path: Path = Path("research/trials.csv")) -> float:
    """P5 报告用的美股账户权重：trials.csv 里最后一行“P5核心合并”的 w_us（账户比例不写进代码；公开版没有这一列）。"""
    t = pd.read_csv(path, low_memory=False)
    if "w_us" not in t:
        raise SystemExit("trials.csv 没有 w_us 列（公开版删掉了账户比例），无法复算合并净值")
    return float(t.loc[t.name == "P5核心合并", "w_us"].dropna().iloc[-1])


def summarize(combs: dict[str, pd.Series], rf: pd.Series, split: str = "2019-12-31") -> dict:
    """combs：三种调仓日的合并净值；收益、波动、夏普按月末调仓口径，最大回撤取三种调仓日最差（和报告一致）。"""
    from quant.metrics import ann_vol, cagr, calmar, max_drawdown, sharpe
    c = combs["end"]
    mdd = min(max_drawdown(s) for s in combs.values())
    return {"window": f"{c.index[0]:%Y-%m-%d} 至 {c.index[-1]:%Y-%m-%d}", "is_cagr": cagr(c.loc[:split]),
            "oos_cagr": cagr(c.loc[split:]), "full_cagr": cagr(c), "mdd_worst": mdd, "mdd_end": max_drawdown(c),
            "ann_vol": ann_vol(c), "sharpe": sharpe(c, rf), "calmar_end": calmar(c), "calmar_worst": cagr(c) / abs(mdd)}


def _p5(get_price, get_index, fx) -> dict[str, pd.Series]:
    from quant.backtest.strategies import rebalance_dates
    from quant.research import p3
    from quant.research.p4 import CORE
    navs = {}
    for label, (e, split, signal) in CORE.items():
        a = p3.ACCOUNTS[label]
        px = p3.build_prices(a, get_price, get_index, fx)[0].loc[:P5_PARAMS["end"]]
        navs[label] = p3.run_trial(px, p3._base_weights(a, e, p3.SPLITS[split]), signal, a, fx,
                                   rebalance_dates(px, "end")[12])[0]
    return {m: p3.combine_navs(navs["美股账户"][m], navs["A股账户"][m], p5_w_us()) for m in ("end", "mid", "start")}


def _aggr(get_price, get_index, fx, getters) -> tuple[dict[str, pd.Series], dict]:
    from quant.backtest.strategies import rebalance_dates
    from quant.research import aggr, p3
    pk = json.loads(aggr.PICK_PATH.read_text())
    navs = {}
    for name in pk["pick"]:
        label, sleeve, eq, sig = name.split("｜")
        a, px, _ = aggr.sleeve_setup(label, sleeve, get_price, get_index, fx, getters)
        base = p3._base_weights(a, int(eq.removeprefix("股").removesuffix("%")) / 100, p3.SPLITS[aggr.SPLIT_NAME])
        navs[label] = p3.run_trial(px, base, sig, a, fx, rebalance_dates(px, "end")[12])[0]
    end = pd.Timestamp(pk["end"])
    combs = {m: p3.combine_navs(navs["美股账户"][m].loc[:end], navs["A股账户"][m].loc[:end], pk["w_us"])
             for m in ("end", "mid", "start")}
    return combs, pk


def main() -> int:
    import warnings
    warnings.filterwarnings("ignore")
    from quant.data.update import get_csindex, get_index, get_price
    from quant.live.plan import default_getters
    fx = {"AUDUSD": get_price("AUDUSD", "FX", "fx"), "AUDCNY": get_price("AUDCNY", "FX", "fx")}
    rf = get_csindex("H11025")  # 中证货币基金指数，人民币无风险收益（与 P4 一致）
    p5 = summarize(_p5(get_price, get_index, fx), rf)
    combs, pk = _aggr(get_price, get_index, fx, default_getters(get_price))
    ag = summarize(combs, rf)
    out = {"rf": "中证货币基金指数 H11025", "P5": {"w_us": p5_w_us(), **P5_PARAMS, **p5},
           "激进版-50%": {"w_us": pk["w_us"], "end": pk["end"], "pick": pk["pick"], "report": "reports/激进版-方案-2026-11-05.md", **ag}}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for k in ("P5", "激进版-50%"):
        print(k, {m: round(v, 4) if isinstance(v, float) else v for m, v in out[k].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
