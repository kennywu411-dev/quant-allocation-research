"""公告因子：汇总标注 → 事件研究 + 月度因子 → reports/公告因子-<日期>.md、同名 png、research/llm_events_results.json。
python -m quant.llm_events.run（先跑 data、label 两步；复核用 --review 200）"""
import argparse
import json
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from quant.factors import evaluate as ev
from quant.llm_events import data, dictionary, label as L, study as S
from quant.research.registry import log_trial, new_run_id

PRICE_DIR = Path("data/cache/factors_current/daily")
SHORT = {"claude-haiku-5-5": "Haiku 5.5", "claude-haiku-4-5": "Haiku 4.5", "dict": "关键词词典"}


def load_prices(codes: list[str]) -> pd.DataFrame:
    cols = {}
    for c in codes:
        p = PRICE_DIR / f"{c}.parquet"
        if p.exists():
            d = pd.read_parquet(p, columns=["date", "close"])
            cols[c] = d.set_index("date").close
    return pd.DataFrame(cols).sort_index()


def segments() -> dict[str, list[tuple[str, str, str]]]:
    """每个标注来源要报告的样本段：(名称, 起, 止)。截止日之后为干净样本。"""
    return {"claude-haiku-4-5": [("截止后（干净）", "2025-08-01", "2026-10-31")],
            "claude-haiku-5-5": [("截止前", "2020-01-01", "2026-06-30"), ("截止后（干净）", "2026-07-01", "2026-10-31"),
                                 ("2025-08 起（与 4.5 同段）", "2025-08-01", "2026-10-31")],
            "dict": [("全期", "2020-01-01", "2026-10-31"), ("2025-08 起", "2025-08-01", "2026-10-31"),
                     ("2026-07 起", "2026-07-01", "2026-10-31")]}


def event_tables(evs: dict, ar: pd.DataFrame) -> tuple[list[dict], dict]:
    rows, series = [], {}
    for src, segs in segments().items():
        e = evs.get(src)
        if e is None or e.empty:
            continue
        for name, a, b in segs:
            x = e[(e.date >= a) & (e.date <= b)]
            for k in S.K:
                cs = S.calendar_series(x, ar, k)
                st = S.spread_stats(cs, k)
                ref = S.spread_stats(S.calendar_series(x, ar, k, include_t0=True), k) if k == S.K_MAIN else {}
                rows.append({"source": src, "segment": name, "start": a, "end": b, "k": k,
                             "n_pos": int((x.group == "利好").sum()), "n_neg": int((x.group == "利空").sum()),
                             **st, "car_incl_t0": ref.get("car", np.nan), "t_incl_t0": ref.get("t", np.nan)})
                if k == S.K_MAIN and not cs.empty and "利好" in cs and "利空" in cs:
                    series[(src, name)] = (cs["利好"] - cs["利空"]).dropna()
    return rows, series


def by_type(e: pd.DataFrame, ar: pd.DataFrame, k: int = S.K_MAIN) -> pd.DataFrame:
    """按事件类型：实质性且有方向的事件，持有 k 天的平均超额（同日聚合、NW t）。"""
    x = e[e.material & e.direction.isin(["利好", "利空"])].copy()
    x["group"] = x["type"] + "｜" + x.direction
    cs = S.calendar_series(x, ar, k)
    out = []
    for g in cs.columns:
        s = cs[g].dropna()
        out.append({"group": g, "n": int((x.group == g).sum()), "car": float(s.mean() * k), "t": S.nw_t(s, k)})
    return pd.DataFrame(out).sort_values("n", ascending=False)


def factor_tests(evs: dict, cal: pd.DatetimeIndex) -> dict:
    from quant.factors import run as frun
    d = frun.load("current")
    idx = d["fwd"].index[(d["fwd"].index >= "2020-01-31") & (d["fwd"].index <= "2026-10-31")]
    out = {}
    for src, e in evs.items():
        f = S.monthly_factor(e, cal, idx).reindex(columns=d["univ"].columns).fillna(0.0)
        univ, fwd = d["univ"].reindex(idx), d["fwd"].reindex(idx)
        ic = ev.ic_series(f, fwd, univ)
        clean_start = {"claude-haiku-4-5": "2025-07-31", "claude-haiku-5-5": "2026-06-30"}.get(src, "2025-07-31")
        full, clean = ev.ic_summary(ic), ev.ic_summary(ic[ic.index > clean_start])
        grp = ev.groups(f, univ, fwd)
        gr = ev.group_returns(grp, fwd)
        ls = ev.long_short(gr, grp) if len(gr) else pd.DataFrame()
        out[src] = {"ic": ic, "summary": {"rank_ic": full["mean"], "t": full["t"], "n_months": full["n"],
                                          "clean_rank_ic": clean["mean"], "clean_t": clean["t"], "clean_n": clean["n"],
                                          "verdict": ev.verdict(full, clean) if clean["n"] else "样本不足",
                                          "ls_net": ev.ann_return(ls.ls_net) if len(ls) else np.nan,
                                          "coverage": float((f.reindex(idx) != 0).where(univ).stack().mean())}}
    return out


def agreement(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    m = a.merge(b, on="id", suffixes=("_a", "_b"))
    if m.empty:
        return {"n": 0}
    po = float((m.direction_a == m.direction_b).mean())
    pa, pb = m.direction_a.value_counts(normalize=True), m.direction_b.value_counts(normalize=True)
    pe = float(sum(pa.get(k, 0) * pb.get(k, 0) for k in set(pa.index) | set(pb.index)))
    act = m[(m.direction_a != "中性") | (m.direction_b != "中性")]  # 至少一方判为有方向的条目
    return {"n": int(len(m)), "direction": po, "kappa": (po - pe) / (1 - pe) if pe < 1 else float("nan"),
            "n_active": int(len(act)), "direction_active": float((act.direction_a == act.direction_b).mean()) if len(act) else float("nan"),
            "material": float((m.material_a == m.material_b).mean()), "type": float((m.type_a == m.type_b).mean())}


def charts(series: dict, types: pd.DataFrame, fac: dict, path: Path) -> None:
    plt.rcParams["font.sans-serif"] = ["PingFang SC", "Heiti SC", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(3, 1, figsize=(10, 13))
    for (src, seg), s in series.items():
        if "2025-08" in seg or "干净" in seg or seg == "全期":
            ax[0].plot(s.cumsum() * 100, label=f"{SHORT[src]}｜{seg}")
    ax[0].axvline(pd.Timestamp("2026-07-01"), color="grey", ls="--", lw=1)
    ax[0].set_title("实质性利好减利空：日历时间组合累计超额（%，持有 5 天，不含公告当日）")
    ax[0].legend(fontsize=8)
    t = types.head(14).iloc[::-1]
    ax[1].barh(t.group, t.car * 100, color=["#3fb950" if v > 0 else "#f85149" for v in t.car])
    ax[1].set_title("按事件类型：持有 5 天平均超额（%，Haiku 4.5 干净样本，事件数最多的 14 组）")
    for src, r in fac.items():
        ax[2].plot(r["ic"].cumsum(), label=SHORT[src])
    ax[2].set_title("月度情绪因子：累计 RankIC")
    ax[2].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _p(x, d=2):
    return "—" if x is None or not np.isfinite(x) else f"{x * 100:.{d}f}%"


def _f(x, d=2):
    return "—" if x is None or not np.isfinite(x) else f"{x:.{d}f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports")
    ap.add_argument("--smoke", action="store_true", help="调试用：不写 trials.csv 和 research/，只输出到 --out")
    a = ap.parse_args(argv)
    ann = data.load_all()
    close = load_prices(sorted(ann.code.unique()))
    from quant.data.update import get_index
    ar = S.abnormal(close, get_index("sh000300"))
    cal = close.index
    labs = {m: L.load_labels(m) for m in ("claude-haiku-5-5", "claude-haiku-4-5")}
    labs["dict"] = dictionary.label(ann)
    evs = {k: S.events(ann, v, cal) for k, v in labs.items() if len(v)}
    rows, series = event_tables(evs, ar)
    types = by_type(evs["claude-haiku-4-5"][evs["claude-haiku-4-5"].date >= S.MAIN_START], ar)
    # 前视偏差：同一段（2025-08 至 2026-06）两个模型的多空序列同日配对
    look = {}
    for tag, inc in (("", False), ("_incl_t0", True)):  # 主口径 + 含公告当日（模型若“记得”当天涨跌，差额最可能出现在这里）
        o = {}
        for src in ("claude-haiku-5-5", "claude-haiku-4-5"):
            e = evs[src]
            x = e[(e.date >= S.OVERLAP[0]) & (e.date <= S.OVERLAP[1])]
            cs = S.calendar_series(x, ar, S.K_MAIN, include_t0=inc)
            o[src] = (cs["利好"] - cs["利空"]).dropna() if {"利好", "利空"} <= set(cs.columns) else pd.Series(dtype=float)
        diff = (o["claude-haiku-5-5"] - o["claude-haiku-4-5"]).dropna()
        look.update({f"h55{tag}": S.spread_stats(pd.DataFrame({"利好": o["claude-haiku-5-5"], "利空": 0.0}), S.K_MAIN),
                     f"h45{tag}": S.spread_stats(pd.DataFrame({"利好": o["claude-haiku-4-5"], "利空": 0.0}), S.K_MAIN),
                     f"diff_car{tag}": float(diff.mean() * S.K_MAIN), f"diff_t{tag}": S.nw_t(diff, S.K_MAIN),
                     f"n_days{tag}": int(len(diff))})
    fac = factor_tests(evs, cal)
    agree = {"h55_vs_h45": agreement(labs["claude-haiku-5-5"], labs["claude-haiku-4-5"])}
    rev = L.load_labels("claude-opus-5-5")
    if len(rev):
        agree["h55_vs_opus"] = agreement(labs["claude-haiku-5-5"], rev)
        agree["h45_vs_opus"] = agreement(labs["claude-haiku-4-5"], rev)
        agree["dict_vs_opus"] = agreement(labs["dict"], rev)
    main_row = next(r for r in rows if r["source"] == S.MAIN_MODEL and r["k"] == S.K_MAIN and "干净" in r["segment"])
    passed = bool(main_row["t"] >= S.T_MAIN and main_row["car"] > 0)
    spend = json.loads((L.DIR / "spend.json").read_text())
    run_id, today = new_run_id(), f"{date.today():%Y-%m-%d}"
    for r in ([] if a.smoke else rows):
        log_trial({"name": f"公告事件｜{SHORT[r['source']]}｜{r['segment']}｜k={r['k']}", "phase": "公告因子",
                   "run_id": run_id, **{k: v for k, v in r.items() if k not in ("source", "segment")}})
    for src, r in ({} if a.smoke else fac).items():
        log_trial({"name": f"公告因子｜{SHORT[src]}", "phase": "公告因子", "run_id": run_id, **r["summary"]})
    stem = f"公告因子-{today}"
    charts(series, types, fac, Path(a.out) / f"{stem}.png")
    res = {"run_id": run_id, "date": today, "n_ann": int(len(ann)), "n_codes": int(ann.code.nunique()),
           "events": rows, "lookahead": look, "main": {**main_row, "passed": passed}, "types": types.to_dict("records"),
           "factor": {k: v["summary"] for k, v in fac.items()}, "agreement": agree, "spend": spend}
    (Path(a.out) / "llm_events_results.json" if a.smoke else Path("research/llm_events_results.json")).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float))
    from quant.llm_events.report import render
    (Path(a.out) / f"{stem}.md").write_text(render(res, f"{stem}.png", ann))
    print(f"主假设：{SHORT[S.MAIN_MODEL]} 干净样本 k=5 多空 {_p(main_row['car'])}，t {_f(main_row['t'])} → {'通过' if passed else '未通过'}")
    print(f"前视：同段 Haiku 5.5 − 4.5 = {_p(look['diff_car'])}（t {_f(look['diff_t'])}）")
    for k, v in fac.items():
        print(f"因子 {SHORT[k]}：RankIC {v['summary']['rank_ic']:.3f} t {v['summary']['t']:.2f}，干净段 {v['summary']['clean_rank_ic']:.3f} → {v['summary']['verdict']}")
    print("花费 $%.2f；报告 %s" % (spend["total"], Path(a.out) / f"{stem}.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
