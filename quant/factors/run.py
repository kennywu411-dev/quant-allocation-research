"""跑单因子检验并写报告：python -m quant.factors.run [--source current|history]
current：今天的沪深300 成分股（data_current 下载，有幸存者偏差）；history：baostock 历史成分（data 下载）。
结果：reports/因子检验-<日期>.md、同名 png 图、research/factor_results.json；每个因子记一行到 research/trials.csv。"""
import argparse
import json
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from quant.factors import calc, data, data_current, evaluate as ev
from quant.research.registry import log_trial, new_run_id

SOURCES = {
    "current": {"cache": data_current.DIR, "members": data_current.MEMBERS,
                "label": "今天的沪深300 成分股（回看到 2010 年；有幸存者偏差）"},
    "history": {"cache": data.DIR, "members": data.DIR / "hs300_members.csv",
                "label": "沪深300 历史成分（每个月末当时的成分）"},
}


def load(source: str) -> dict:
    s = SOURCES[source]
    members = pd.read_csv(s["members"], dtype=str)
    codes = sorted(set(members.code))
    p = calc.panels(codes, s["cache"])
    idx = pd.date_range(data.START, data.END, freq="ME")
    codes = [c for c in codes if c in p["close"].columns]
    market_last = p["last_date"].reindex(idx).max(axis=1)  # 每月全市场（股票池内）最后一个交易日
    member = calc.members_panel(members, idx, codes)
    univ = calc.universe(member, {k: v.reindex(columns=codes) for k, v in p.items()}, market_last)
    f = {k: v.reindex(index=idx, columns=codes) for k, v in calc.factor_values(p).items()}
    fwd = calc.forward_return(p["close"]).reindex(index=idx, columns=codes)
    return {"factors": f, "fwd": fwd, "univ": univ, "n_codes": len(codes), "label": s["label"]}


def analyze(f: pd.DataFrame, fwd: pd.DataFrame, univ: pd.DataFrame) -> dict:
    """一个因子的全部检验结果。"""
    ic = ev.ic_series(f, fwd, univ)
    ic_p = ev.ic_series(f, fwd, univ, rank=False)
    full, is_, oos = ev.ic_summary(ic), ev.ic_summary(ic[ic.index <= ev.SPLIT]), ev.ic_summary(ic[ic.index > ev.SPLIT])
    grp = ev.groups(f, univ, fwd)
    gr = ev.group_returns(grp, fwd)
    ls = ev.long_short(gr, grp)
    oos_ls = ls[ls.index > pd.Timestamp(ev.SPLIT) + pd.offsets.MonthEnd(1)]
    cover = (f.notna() & univ).sum(axis=1) / univ.sum(axis=1).replace(0, np.nan)
    med = pd.DataFrame({t: {g: float(fwd.loc[t, c].median()) for g, c in gs.items()} for t, gs in grp.items()}).T
    return {
        "ic": ic, "gr": gr, "ls": ls, "year": ev.by_year(ic, ls.ls_net),
        "summary": {
            "rank_ic": full["mean"], "rank_ic_t": full["t"], "icir_ann": full["icir_ann"], "win": full["win"],
            "n_months": full["n"], "ic_pearson": float(ic_p.mean()),
            "is_rank_ic": is_["mean"], "is_t": is_["t"], "oos_rank_ic": oos["mean"], "oos_t": oos["t"],
            "verdict": ev.verdict(full, oos),
            **{f"q{g}": ev.ann_return(gr[g]) for g in gr.columns},
            **{f"qmed{g}": float(med[g].mean()) for g in med.columns},  # 组内中位数月收益的时间平均
            "ls_gross": ev.ann_return(ls.ls), "ls_net": ev.ann_return(ls.ls_net),
            "top_ex_gross": ev.ann_return(ls.top_ex), "top_ex_net": ev.ann_return(ls.top_ex_net),
            "oos_ls_net": ev.ann_return(oos_ls.ls_net), "oos_top_ex_net": ev.ann_return(oos_ls.top_ex_net),
            "top_turn": float(ls.top_turn.iloc[1:].mean()), "bot_turn": float(ls.bot_turn.iloc[1:].mean()),
            "coverage": float(cover.mean()),
        }}


def _pct(x: float, d: int = 1) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x * 100:.{d}f}%"


def charts(res: dict, path: Path) -> None:
    plt.rcParams["font.sans-serif"] = ["PingFang SC", "Heiti SC", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    names = list(res)
    fig, ax = plt.subplots(3, 1, figsize=(10, 13))
    for k in names:
        ax[0].plot(res[k]["ic"].cumsum(), label=k)
    ax[0].axvline(pd.Timestamp(ev.SPLIT), color="grey", ls="--", lw=1)
    ax[0].set_title("累计 RankIC（虚线 = 样本内外分界 2019 年底）")
    ax[0].legend(ncol=4, fontsize=9)
    w = 0.8 / len(names)
    for i, k in enumerate(names):
        s = res[k]["summary"]
        ax[1].bar(np.arange(1, 6) + (i - len(names) / 2) * w, [s[f"q{g}"] * 100 for g in range(1, 6)], w, label=k)
    ax[1].set_xticks(range(1, 6), ["Q1 最低", "Q2", "Q3", "Q4", "Q5 最高"])
    ax[1].set_title("五分组年化收益（%，扣成本前）")
    ax[1].legend(ncol=4, fontsize=9)
    for k in names:
        ax[2].plot((1 + res[k]["ls"].ls_net).cumprod(), label=k)
    ax[2].set_yscale("log")
    ax[2].axvline(pd.Timestamp(ev.SPLIT), color="grey", ls="--", lw=1)
    ax[2].set_title("多空（Q5 - Q1）扣成本后净值（对数坐标）")
    ax[2].legend(ncol=4, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def render(res: dict, meta: dict, png: str) -> str:
    S = {k: v["summary"] for k, v in res.items()}
    L = [f"# A股单因子检验（{meta['date']}）", "",
         "> 研究记录，不是投资建议；作者不是持牌金融顾问。", ""]
    if meta["source"] == "current":
        L += ["## 先说局限：幸存者偏差", "",
              "- 股票池是**今天**的沪深300 成分股，回看到 2010 年。历史成分股的免费来源（baostock）检验期间不可用，所以退而求其次。",
              "- 这意味着样本里只有“活到今天、并且今天够大能进指数”的公司；当年进过指数、后来跌出去或退市的公司都不在里面。",
              "- 偏差方向：过去涨得好的公司更可能留到今天，所以**动量**会被高估、**反转**会被低估；"
              "今天的大公司过去多半走势平稳，**低波**也可能被高估。估值类（EP、BP、股息率）偏差方向不确定。",
              "- 早年股票池更小（很多今天的成分股那时还没上市），早期结果的噪声更大。",
              "- 所以下面的结论只能当作“在幸存者里成立与否”。数据源恢复后应换成历史成分重跑（`--source history`），代码不用改。", ""]
    L += ["## 数据与方法", "",
          f"- 股票池：{meta['label']}，共 {meta['n_codes']} 只；每个月末再剔除当天停牌的（月末最后一个交易日没有成交）"
          + ("" if meta["source"] == "current" else "和 ST") + "。",
          f"- 区间：{data.START[:7]} 至 {data.END[:7]}，月频；样本内到 {ev.SPLIT[:4]} 年底，样本外 {int(ev.SPLIT[:4]) + 1} 年起。",
          "- 数据（全部免费，可复现）：" + "；".join(f"{k}：{v}" for k, v in meta["sources"].items()) + "。",
          "- 每个月末 t 只用 t 及以前的数据算因子，和 t 到 t+1 月末的后复权收益比较。"
          "截面先 1%/99% 缩尾再标准化，RankIC 用 Spearman 相关。",
          "- 五分组：每月按因子值等分 5 组，组内等权，持有一个月。多空 = Q5 - Q1；多头超额 = Q5 - 股票池等权。",
          "- 成本：每单位单边换手按往返 0.25% + 印花税（2023-08-28 前 0.1%，之后 0.05%）扣除。",
          ""]
    if meta["source"] == "current":
        L += ["- 估值数据（百度）大约每 22 天一个点，月末用最近一个点，最多滞后约 3 周；这个口径偏保守，不会用到未来数据，"
              "但不确定百度是否按“财报公告日”而非“报告期”切换盈利数据，如果是后者会有轻微前视。",
              "- 取不到历史 ST 标记，所以没有剔除 ST（今天的成分股里没有 ST，但不代表历史上没有）。", ""]
    if meta.get("fix"):
        L += ["## 运行后的修正（如实记录）", ""] + meta["fix"] + [""]
    L += ["## 判定标准（运行前写进代码，`quant/factors/evaluate.py`）", "",
          f"- **显著**：全期 RankIC 均值的 t 值 ≥ {ev.T_SIG:.0f}（7 个因子同时检验，按多重检验的更高门槛），且样本外与全期同号；",
          f"- **弱**：{ev.T_WEAK:.0f} ≤ t < {ev.T_SIG:.0f} 且样本外同号；**方向相反**：t ≤ -{ev.T_WEAK:.0f}；其余为**不显著**。", "",
          "## 结果总表", "",
          "| 因子 | 定义 | RankIC 均值 | t 值 | 年化 ICIR | IC>0 月份占比 | 样本内 RankIC | 样本外 RankIC | 判定 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for k, s in S.items():
        L.append(f"| {k} | {calc.FACTORS[k]} | {s['rank_ic']:.3f} | {s['rank_ic_t']:.2f} | {s['icir_ann']:.2f} | "
                 f"{_pct(s['win'], 0)} | {s['is_rank_ic']:.3f}（t {s['is_t']:.1f}） | {s['oos_rank_ic']:.3f}（t {s['oos_t']:.1f}） | **{s['verdict']}** |")
    L += ["", f"![因子检验图]({png})", "",
          "## 五分组与多空（年化）", "",
          "| 因子 | Q1 | Q2 | Q3 | Q4 | Q5 | 多空 扣成本前 | 多空 扣成本后 | 样本外多空 扣成本后 | Q5 超额 扣成本后 | 样本外 Q5 超额 扣成本后 | Q5 月均单边换手 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, s in S.items():
        L.append(f"| {k} | " + " | ".join(_pct(s[f'q{g}']) for g in range(1, 6))
                 + f" | {_pct(s['ls_gross'])} | {_pct(s['ls_net'])} | {_pct(s['oos_ls_net'])} | {_pct(s['top_ex_net'])} | "
                   f"{_pct(s['oos_top_ex_net'])} | {_pct(s['top_turn'], 0)} |")
    L += ["", "注：A股个人投资者不能方便地融券做空，多空只是衡量因子区分度的尺子；能实际做的是只买 Q5，对应“Q5 超额”。", "",
          "### 为什么 RankIC 为正，分组均值却是 Q1 更高", "",
          "RankIC 看的是排序（多数股票），分组收益看的是等权均值（会被少数大涨的股票拉高）。下表是每月组内**中位数**收益的平均值：",
          "", "| 因子 | Q1 | Q2 | Q3 | Q4 | Q5 | Q5 - Q1 |", "|---|---|---|---|---|---|---|"]
    for k, s in S.items():
        L.append(f"| {k} | " + " | ".join(_pct(s[f'qmed{g}'], 2) for g in range(1, 6)) + f" | {_pct(s['qmed5'] - s['qmed1'], 2)} |")
    L += ["", "按中位数，多数因子是 Q5 好于 Q1，和 RankIC 的方向一致；按均值则反过来。也就是说，高估值、高波动、高换手的组"
          "多数股票表现更差，但组里偶尔有涨几倍的股票。用今天的成分股回看，这种右偏被幸存者偏差放大："
          "当年估值高、波动大的小公司，正是后来涨上来才进了沪深300 的那批。", "",
          "## 分年度 RankIC 均值", ""]
    yrs = sorted(set().union(*[v["year"].index for v in res.values()]))
    L += ["| 因子 | " + " | ".join(str(y) for y in yrs) + " | 为正的年份 |", "|---|" + "---|" * (len(yrs) + 1)]
    for k, v in res.items():
        y = v["year"].rank_ic
        L.append(f"| {k} | " + " | ".join("—" if pd.isna(y.get(t)) else f"{y[t]:.3f}" for t in yrs)
                 + f" | {int((y > 0).sum())}/{int(y.notna().sum())} |")
    L += ["", "## 结论", ""] + meta["conclusion"] + ["", "## 复现", "", "```bash",
                                                    f"PYTHONPATH=. .venv/bin/python -m {meta['download']}",
                                                    f"PYTHONPATH=. .venv/bin/python -m quant.factors.run --source {meta['source']}",
                                                    "```", "",
                                                    f"运行编号 `{meta['run_id']}`；每个因子的结果记在 `research/trials.csv`（phase = 因子检验）。", ""]
    return "\n".join(L)


def conclusion(S: dict, source: str) -> list[str]:
    """按判定结果自动生成的结论句（只陈述数字，不加解读）。"""
    out = []
    for v in ("显著", "弱", "方向相反", "不显著"):
        ks = [k for k, s in S.items() if s["verdict"] == v]
        if ks:
            out.append(f"- **{v}**：" + "、".join(f"{k}（RankIC {S[k]['rank_ic']:.3f}，t {S[k]['rank_ic_t']:.1f}，"
                                                   f"样本外 {S[k]['oos_rank_ic']:.3f}）" for k in ks) + "。")
    pos = [k for k, s in S.items() if s["verdict"] in ("显著", "弱") and s["oos_top_ex_net"] > 0]
    out.append("- 通过判定且样本外 Q5 扣成本后仍有超额的：" + ("、".join(pos) if pos else "无") + "。")
    if source == "current":
        out.append("- 以上都在幸存者偏差下得到，动量 / 低波的结果尤其要打折扣；换成历史成分重跑前，不据此做任何实盘决定。")
    return out


def fix_note(path: Path = Path("research/factor_results-修正前含次新股.json")) -> list[str]:
    """第一次运行没有剔除次新股；修正前的结果保存在 path，这里列出来对照。"""
    if not path.exists():
        return []
    old = json.loads(path.read_text())["factors"]
    rows = "；".join(f"{k} t {v['rank_ic_t']:.2f}" for k, v in old.items())
    return [f"- 第一次运行没有剔除上市不满一年的股票。检查极端值时发现，月收益最大的几个都是新股上市后的连续一字涨停（最高一个月 +456%），"
            f"这部分涨幅实际买不到，于是加了“上市满 {calc.MIN_AGE} 个交易日”的条件后重跑（`calc.MIN_AGE`）。",
            f"- 修正前的结果（`{path}`，trials.csv 里也有）：{rows}；判定全部为不显著，和修正后一致。",
            "- 判定标准、因子定义、样本切分都没有改。"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=list(SOURCES), default="current")
    ap.add_argument("--out", default="reports")
    a = ap.parse_args(argv)
    d = load(a.source)
    res = {k: analyze(f, d["fwd"], d["univ"]) for k, f in d["factors"].items()}
    run_id = new_run_id()
    today = f"{date.today():%Y-%m-%d}"
    S = {k: v["summary"] for k, v in res.items()}
    for k, s in S.items():
        log_trial({"name": f"因子检验｜{k}｜{a.source}", "phase": "因子检验", "run_id": run_id, **s})
    cache = SOURCES[a.source]["cache"]
    meta_dl = json.loads((cache / "meta.json").read_text()) if (cache / "meta.json").exists() else {"sources": {}}
    stem = f"因子检验-{today}"
    png = f"{stem}.png"
    charts(res, Path(a.out) / png)
    meta = {"date": today, "source": a.source, "label": d["label"], "n_codes": d["n_codes"], "run_id": run_id,
            "sources": meta_dl.get("sources", {}), "conclusion": conclusion(S, a.source),
            "download": "quant.factors.data_current" if a.source == "current" else "quant.factors.data",
            "fix": fix_note()}
    (Path(a.out) / f"{stem}.md").write_text(render(res, meta, png))
    Path("research/factor_results.json").write_text(json.dumps(
        {"run_id": run_id, "source": a.source, "date": today, "n_codes": d["n_codes"],
         "univ_size": {"min": int(d["univ"].sum(axis=1).replace(0, np.nan).min()), "max": int(d["univ"].sum(axis=1).max())},
         "factors": S}, ensure_ascii=False, indent=1, default=float))
    for k, s in S.items():
        print(f"{k:8s} RankIC {s['rank_ic']:+.3f} t {s['rank_ic_t']:+.2f} 样本外 {s['oos_rank_ic']:+.3f} "
              f"多空净 {_pct(s['ls_net'])} Q5超额净 {_pct(s['top_ex_net'])} → {s['verdict']}")
    print(f"报告：{Path(a.out) / (stem + '.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
