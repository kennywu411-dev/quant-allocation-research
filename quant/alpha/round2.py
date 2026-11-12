"""因子挖掘第二轮（登记见 spec.py 的 R2_*）：python -m quant.alpha.round2
不加新因子，只改持仓构造。→ reports/因子挖掘第二轮-<日期>.md、research/alpha_round2.json；每个试验记一行 trials.csv。"""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant.alpha import evaluate as E, spec
from quant.factors import evaluate as fev


def neutralize(f: pd.DataFrame, by: pd.DataFrame, univ: pd.DataFrame) -> pd.DataFrame:
    """每月在股票池内把 f 对 by 做一元回归（带截距），返回残差；任一缺失的为 NaN。"""
    out = pd.DataFrame(np.nan, index=f.index, columns=f.columns)
    for t in f.index:
        m = univ.loc[t]
        d = pd.DataFrame({"y": f.loc[t, m[m].index], "x": by.loc[t, m[m].index]}).dropna()
        if len(d) < 30 or d.x.var() == 0:
            continue
        beta = d.y.cov(d.x) / d.x.var()
        out.loc[t, d.index] = d.y - d.y.mean() - beta * (d.x - d.x.mean())
    return out


def buffered_sets(f: pd.DataFrame, univ: pd.DataFrame, n: int = spec.N_GROUPS, exit_q: float = spec.R2_EXIT) -> dict:
    """缓冲带目标持仓 {调仓日: 集合}：持有 N = 池内股票数 / n 只；已持有、排名仍在前 exit_q 的留下
    （多于 N 时留排名最高的 N 只），空位按排名从高到低补。只用当期因子值和上期目标。"""
    out, prev = {}, set()
    for t in f.index:
        m = univ.loc[t]
        x = f.loc[t, m[m].index].dropna()
        if len(x) < n * 20:
            continue
        order = x.rank(method="first", ascending=False).sort_values()  # 1 = 最好
        N = len(x) // n
        keep = [c for c in order.index if c in prev and order[c] <= exit_q * len(x)][:N]
        ks = set(keep)
        fill = [c for c in order.index if c not in ks][:N - len(keep)]
        prev = ks | set(fill)
        out[t] = prev
    return out


def top_sets(f: pd.DataFrame, univ: pd.DataFrame) -> dict:
    return {t: s[1] for t, s in E.quantile_sets(f, univ).items()}


def ex_bottom_sets(f: pd.DataFrame, univ: pd.DataFrame) -> dict:
    """股票池里除因子最低五分之一以外的全部股票（因子缺失的也留着）。"""
    out = {}
    for t, s in E.quantile_sets(f, univ).items():
        m = univ.loc[t]
        out[t] = set(m[m].index) - s[0]
    return out


def evaluate(target: dict, fwd, univ, up, dn, tradable) -> dict:
    """纯多头组合相对股票池等权的月度净超额及汇总。"""
    from quant.llm_events.study import nw_t
    top = E.simulate(target, fwd, up, dn, tradable)
    bench = pd.Series({fev.hold_label(t): float(fwd.loc[t, univ.loc[t]].fillna(0).mean()) for t in target})
    ex = (top.net - bench.reindex(top.index)).dropna()
    gross_ex = (top.gross - bench.reindex(top.index)).dropna()
    o = lambda s: s[s.index > pd.Timestamp(spec.SPLIT) + pd.offsets.MonthEnd(1)]
    i = lambda s: s[s.index <= pd.Timestamp(spec.SPLIT) + pd.offsets.MonthEnd(1)]
    ann = fev.ann_return
    s = {"n": int(len(ex)), "ex_ann": ann(ex), "ex_t": nw_t(ex, 3), "is_ex_ann": ann(i(ex)), "oos_ex_ann": ann(o(ex)),
         "oos_ex_t": nw_t(o(ex), 3), "gross_ex_ann": ann(gross_ex), "ex_mdd": E.max_drawdown(ex), "oos_ex_mdd": E.max_drawdown(o(ex)),
         "top_turn": float(top.turn.iloc[1:].mean()), "top_ann_net": ann(top.net), "top_mdd": E.max_drawdown(top.net),
         "bench_ann": ann(bench.reindex(top.index)), "n_hold": float(top.n.mean()),
         "by_year": {int(y): float((1 + g).prod() - 1) for y, g in ex.groupby(ex.index.year)}}
    return {"excess": ex, "summary": s}


def main(argv: list[str] | None = None) -> int:
    import warnings
    warnings.filterwarnings("ignore")
    from quant.alpha.weekly import build
    from quant.research.registry import log_trial, new_run_id
    from quant.research.stats import deflated_sharpe
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerun", default="", help="勘误重跑时的标记，写进 trials.csv 的名称后缀（不计新试验）")
    a = ap.parse_args(argv)
    b = build()
    f, fwd, univ = b["f"], b["fwd"], b["univ"]
    args = (fwd, univ, b["up"], b["dn"], b["tradable"])
    z = {k: E.zscores(v, univ) for k, v in f.items()}
    ew = E.equal_weighted(z)
    slow = E.equal_weighted({k: z[k] for k in spec.R2_SLOW})
    size_z = z["SIZE"]
    targets = {
        "慢因子合成": top_sets(slow, univ),
        "等权合成+缓冲带": buffered_sets(ew, univ),
        "慢因子合成+缓冲带": buffered_sets(slow, univ),
        "等权合成（市值中性）": top_sets(neutralize(ew, size_z, univ), univ),
        "IVOL（市值中性）": top_sets(neutralize(z["IVOL"], size_z, univ), univ),
        "剔除最差组": ex_bottom_sets(ew, univ),
    }
    assert list(targets) == list(spec.R2_TRIALS)
    res = {k: evaluate(v, *args) for k, v in targets.items()}
    ref = {"等权合成（第一轮，对照）": evaluate(top_sets(ew, univ), *args)}
    srs = [r["excess"].mean() / r["excess"].std() for r in res.values()]
    r1 = json.loads(Path("research/alpha_results.json").read_text())
    var_sr = max(float(np.var(srs, ddof=1)), float(r1["var_sr"]))
    run_id, today = new_run_id(), f"{date.today():%Y-%m-%d}"
    for k, r in {**res, **ref}.items():
        s = r["summary"]
        s["dsr"] = deflated_sharpe(r["excess"], spec.R2_N_TRIALS, var_sr)
        s["passed"] = bool(s["ex_t"] >= spec.R2_T_PASS and s["oos_ex_ann"] > 0)
        s["shadow"] = bool(s["passed"] and s["dsr"] >= spec.R2_DSR_PASS)
    for k, r in res.items():
        log_trial({"name": f"因子挖掘第二轮｜{k}｜全A{a.rerun}", "phase": "因子挖掘", "run_id": run_id,
                   **{kk: v for kk, v in r["summary"].items() if kk != "by_year"}})
    S = {k: r["summary"] for k, r in {**res, **ref}.items()}
    meta = {"run_id": run_id, "date": today, "var_sr": var_sr, "n_trials": spec.R2_N_TRIALS}
    Path("research/alpha_round2.json").write_text(json.dumps({**meta, "trials": S}, ensure_ascii=False, indent=1, default=float))
    for k, s in S.items():
        print(f"{k:14s} 超额 {s['ex_ann']:+.1%} t {s['ex_t']:+.2f} 样本内 {s['is_ex_ann']:+.1%} 样本外 {s['oos_ex_ann']:+.1%} (t {s['oos_ex_t']:+.2f}) "
              f"换手 {s['top_turn']:.0%} 超额回撤 {s['ex_mdd']:+.1%} DSR {s['dsr']:.2f} → {'影子盘候选' if s['shadow'] else '通过' if s['passed'] else '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
