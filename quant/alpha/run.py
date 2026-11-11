"""因子挖掘主程序：python -m quant.alpha.run → reports/因子挖掘-<日期>.md、同名 png、research/alpha_results.json；每个检验记一行 trials.csv。"""
import argparse
import json
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from quant.alpha import calc, data, evaluate as E, spec
from quant.llm_events.study import nw_t
from quant.research.registry import log_trial, new_run_id
from quant.research.stats import deflated_sharpe


def build() -> dict:
    mem = pd.read_csv(data.DIR / "all_members.csv", dtype=str)
    basic = pd.read_csv(data.DIR / "stock_basic.csv", dtype=str)
    codes = sorted(set(mem.code))
    p = calc.load_daily(codes)
    days = p["close"].index
    ret = calc.daily_returns(p)
    mcap = calc.float_mcap(p)
    up, dn = calc.limit_flags(p, calc.limit_pct(p["close"].columns, days, p["isST"]))
    me = calc.month_end_dates(days)
    me = me[(me >= spec.START) & (me <= spec.END)]
    f = calc.factors(p, ret, mcap, me)
    fwd = calc.forward_returns(ret, calc.month_end_dates(days)).reindex(me)
    univ = calc.universe(mem, p, mcap, me, basic)
    tradable = (p["tradestatus"].reindex(me) == 1).fillna(False)
    return {"f": f, "fwd": fwd, "univ": univ, "up": up.reindex(me).fillna(False), "dn": dn.reindex(me).fillna(False),
            "tradable": tradable, "n_codes": len(codes), "univ_size": univ.sum(axis=1)}


def charts(res: dict, path: Path) -> None:
    plt.rcParams["font.sans-serif"] = ["PingFang SC", "Heiti SC", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(3, 1, figsize=(10, 13))
    for k, r in res.items():
        ax[0].plot(r["ic"].cumsum(), label=k, lw=2.2 if "合成" in k else 1)
    ax[0].axvline(pd.Timestamp(spec.SPLIT), color="grey", ls="--", lw=1)
    ax[0].set_title("累计 RankIC（虚线 = 样本内外分界）")
    ax[0].legend(ncol=5, fontsize=8)
    names = list(res)
    vals = [res[k]["summary"]["oos_ex_ann"] * 100 for k in names]
    ax[1].bar(names, vals, color=["#3fb950" if res[k]["summary"]["passed"] else "#8b949e" for k in names])
    ax[1].set_title("样本外纯多头年化超额（%，扣成本、涨跌停约束；绿色 = 通过全部门槛）")
    ax[1].tick_params(axis="x", rotation=45)
    for k in names:
        if "合成" in k or res[k]["summary"]["passed"]:
            ax[2].plot((1 + res[k]["excess"]).cumprod(), label=k)
    ax[2].axvline(pd.Timestamp(spec.SPLIT), color="grey", ls="--", lw=1)
    ax[2].set_title("纯多头超额净值（最高组 − 股票池等权，扣成本）")
    ax[2].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    import warnings
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports")
    a = ap.parse_args(argv)
    d = build()
    args = (d["fwd"], d["univ"], d["up"], d["dn"], d["tradable"])
    res = {k: E.summarize(v, *args) for k, v in d["f"].items()}
    z = {k: E.zscores(v, d["univ"]) for k, v in d["f"].items()}
    comps = {"等权合成": E.equal_weighted(z),
             "IC加权合成": E.ic_weighted(z, {k: r["ic"] for k, r in res.items()}),
             "LightGBM合成": E.lgb_composite(d["f"], d["fwd"], d["univ"])}
    for k, v in comps.items():
        res[k] = E.summarize(v, *args)
    # 多重检验补充：纯多头超额的通缩夏普（按 15 次试验、各试验夏普的方差折扣）
    srs = {k: r["excess"].mean() / r["excess"].std() for k, r in res.items() if len(r["excess"]) > 12}
    var_sr = float(np.var(list(srs.values()), ddof=1))
    for k, r in res.items():
        r["summary"]["dsr"] = deflated_sharpe(r["excess"], spec.N_TRIALS, var_sr) if k in srs else float("nan")
    # 机器学习 vs 线性：样本外逐月 RankIC 差
    oos = lambda s: s[s.index > spec.SPLIT]
    ml = {}
    for lin in ("等权合成", "IC加权合成"):
        dd = (oos(res["LightGBM合成"]["ic"]) - oos(res[lin]["ic"])).dropna()
        ml[lin] = {"diff": float(dd.mean()), "t": nw_t(dd, 3), "n": int(len(dd))}
    run_id, today = new_run_id(), f"{date.today():%Y-%m-%d}"
    S = {k: r["summary"] for k, r in res.items()}
    for k, s in S.items():
        log_trial({"name": f"因子挖掘｜{k}｜全A", "phase": "因子挖掘", "run_id": run_id, **s})
    stem = f"因子挖掘-{today}"
    charts(res, Path(a.out) / f"{stem}.png")
    meta = {"run_id": run_id, "date": today, "n_codes": d["n_codes"],
            "univ_min": int(d["univ_size"].replace(0, np.nan).min()), "univ_max": int(d["univ_size"].max()),
            "univ_median": int(d["univ_size"].median()), "ml_vs_linear": ml, "var_sr": var_sr}
    Path("research/alpha_results.json").write_text(json.dumps({**meta, "factors": S}, ensure_ascii=False, indent=1, default=float))
    from quant.alpha.report import render
    (Path(a.out) / f"{stem}.md").write_text(render(S, meta, f"{stem}.png"))
    n_pass = sum(s["passed"] for s in S.values())
    print(f"试了 {len(S)} 个，通过 {n_pass} 个")
    for k, s in S.items():
        print(f"{k:12s} RankIC {s['rank_ic']:+.3f} t {s['t']:+.2f} 样本外 {s['oos_rank_ic']:+.3f} 纯多头样本外 {s['oos_ex_ann']:+.1%} DSR {s['dsr']:.2f} → {'通过' if s['passed'] else '-'}")
    print("LightGBM − 线性（样本外 RankIC）：", {k: f"{v['diff']:+.3f} (t {v['t']:.2f})" for k, v in ml.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
