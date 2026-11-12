"""因子线月度流水线（只记账、不下单）：python -m quant.alpha.pipeline [--source tushare] [--asof 2026-11-30]

  1 更新数据（--source：tushare（默认，2026-11-12 起）= 由本地 Tushare 日线缓存合成周线（先跑 quant.tsdata.download）；cache = 本地 baostock 周线缓存；
     baostock = 增量更新尚未实现，会明确报错而不是静默跳过）
  2 读最新缓存 → 算因子（注册表）→ 最近一个走完的调仓日的目标持仓
  3 追加观察盘记录（已有记录不覆盖）
  4 计算相邻两期记录之间的实际收益 → live/alpha_shadow/returns.csv
  5 偏差与监控报告 → reports/因子监控-<日期>.md、research/alpha_monitor.json（看板读取）

不产生新试验：只用 spec.py 已登记的因子和持仓规则，不写 trials.csv，不改任何判定结果。"""
import argparse
import json
from pathlib import Path

import pandas as pd

from quant.alpha import shadow, spec
from quant.alpha.weekly_data import WDIR
from quant.factors import evaluate as fev

MONITOR_JSON = Path("research/alpha_monitor.json")
DEFAULT_SOURCE = "tushare"  # 2026-11-12 用户决定：baostock 周线缓存没法增量更新，默认改用 Tushare
IC_WINDOW = 12


def _cache(cache: Path) -> dict:
    files = sorted(Path(cache).glob("*.parquet"))
    last = max(pd.read_parquet(p, columns=["date"]).date.max() for p in files)
    return {"source": "cache", "files": len(files), "last_week": str(pd.Timestamp(last).date())}


def _tushare(cache: Path, ts_root: Path | None = None, alpha_dir: Path | None = None) -> dict:
    """由本地 Tushare 缓存合成周线、名单和上市日（联网下载由 `python -m quant.tsdata.download` 另行完成）。"""
    from quant.alpha import ts_weekly
    kw = {k: v for k, v in (("root", ts_root), ("out", alpha_dir)) if v is not None}
    return ts_weekly.convert(**kw)


def data_paths(source: str, alpha_dir: Path | None = None) -> dict:
    """weekly.build 读哪一套周线、名单、上市日。"""
    from quant.alpha import data
    d = Path(alpha_dir) if alpha_dir is not None else data.DIR
    if source == "tushare":
        return {"cache": d / "weekly_ts", "members": d / "all_members_ts.csv", "basic": d / "stock_basic_ts.csv"}
    return {"cache": d / "weekly", "members": d / "all_members.csv", "basic": d / "stock_basic.csv"}


def _baostock(cache: Path) -> dict:
    raise NotImplementedError("baostock 周线增量更新尚未实现（现有下载器只下固定区间、已存在的文件不重下）；且 baostock 只能单进程")


SOURCES = {"cache": _cache, "tushare": _tushare, "baostock": _baostock}


def update_data(source: str, cache: Path = WDIR, ts_root: Path | None = None, alpha_dir: Path | None = None) -> dict:
    if source not in SOURCES:
        raise ValueError(f"未知数据源 {source}；可选 {list(SOURCES)}")
    if source == "tushare":
        return _tushare(cache, ts_root, alpha_dir)
    return SOURCES[source](cache)


def ic_alerts(ics: dict[str, pd.Series], window: int = IC_WINDOW) -> dict:
    """各因子全期与最近 window 个月的 RankIC 均值；最近均值 ≤ 0 记为告警（只提示，不自动改动任何东西）。"""
    out = {}
    for k, ic in ics.items():
        ic = ic.dropna()
        recent = float(ic.iloc[-window:].mean())
        out[k] = {"full": float(ic.mean()), "recent": recent, "n_recent": int(min(window, len(ic))), "alert": bool(recent <= 0)}
    return out


def deviation(real: pd.DataFrame, backtest: dict) -> pd.DataFrame:
    """观察盘毛收益 − 回测口径毛收益（同一持有期、同一组合）。backtest = {组合: {起始调仓日: 毛收益}}。"""
    d = real[["start", "end", "portfolio", "gross"]].copy()
    d["backtest_gross"] = [backtest.get(p, {}).get(s, float("nan")) for p, s in zip(d.portfolio, d.start)]
    d["diff"] = d.gross - d.backtest_gross
    return d


def _pct(x):
    return "—" if pd.isna(x) else f"{x * 100:+.2f}%"


def render(m: dict) -> str:
    L = [f"# 因子观察盘监控（{m['asof']}）", "",
         "> 研究记录，不是投资建议；作者不是持牌金融顾问；历史回测不代表未来收益。观察盘只记账、不下单；"
         "跟踪的两个组合在第二轮**没有通过**预先登记的门槛。", "",
         "## 数据", "",
         f"- 数据源：{m['data']['source']}；周线文件 {m['data']['files']:,} 个，最新一周 {m['data']['last_week']}，距今天 {m['stale_days']} 天。",
         f"- 最近一个走完的调仓日：{m['rebalance']}；本次{'新写入' if m['recorded'] else '已有'}观察盘记录；股票池 {m['universe_n']:,} 只。",
         "- 局限：`cache` 数据源的股票名单和周线止于下载当时；`tushare` 数据源每次由本地 Tushare 缓存重新合成，需先运行 `python -m quant.tsdata.download`。", "",
         "## 持仓", "", "| 组合 | 目标只数 | 实际可持有 | 与上一期重合 |", "|---|---:|---:|---:|"]
    for k, h in m["holdings"].items():
        L.append(f"| {k} | {h['target_n']} | {h['held_n']} | {'首期' if h['overlap'] is None else format(h['overlap'], '.0%')} |")
    L += ["", "## 已实现收益（相邻两期记录之间，扣成本，相对股票池等权）", ""]
    if m["realized"]:
        L += ["| 持有期 | 组合 | 只数 | 毛收益 | 换手 | 净收益 | 股票池等权 | 净超额 |", "|---|---|---:|---:|---:|---:|---:|---:|"]
        L += [f"| {r['start']} → {r['end']} | {r['portfolio']} | {r['n']} | {_pct(r['gross'])} | {r['turn']:.0%} | {_pct(r['net'])} | {_pct(r['bench'])} | {_pct(r['excess'])} |" for r in m["realized"]]
    else:
        L.append("- 还没有走完的持有期（只有一期记录），暂无收益数字。")
    L += ["", "## 与回测的偏差（观察盘毛收益 − 回测口径毛收益）", ""]
    if m["deviation"]:
        L += ["| 持有期 | 组合 | 观察盘 | 回测口径 | 偏差 |", "|---|---|---:|---:|---:|"]
        L += [f"| {r['start']} → {r['end']} | {r['portfolio']} | {_pct(r['gross'])} | {_pct(r['backtest_gross'])} | {_pct(r['diff'])} |" for r in m["deviation"]]
        L.append("")
        L.append("- 回测口径 = 同一调仓日的目标持仓等权、不含涨跌停约束；偏差来自涨停买不进、跌停卖不出，以及记录之后的数据修订。")
    else:
        L.append("- 暂无可比的持有期。")
    L += ["", f"## 因子 RankIC 监控（最近 {IC_WINDOW} 个月均值 ≤ 0 记为告警，只提示）", "",
          "| 因子 | 全期 RankIC | 最近均值 | 告警 |", "|---|---:|---:|---|"]
    L += [f"| {k} | {a['full']:.3f} | {a['recent']:.3f} | {'⚠ 是' if a['alert'] else '否'} |" for k, a in m["ic_alerts"].items()]
    L += ["", "## 复现", "", "```bash", f"PYTHONPATH=. .venv/bin/python -m quant.alpha.pipeline --source {m['data']['source']}", "```", ""]
    return "\n".join(L)


def run(source: str = DEFAULT_SOURCE, asof=None, shadow_dir: Path = shadow.OUT, report_dir: Path = Path("reports"),
        monitor_json: Path = MONITOR_JSON) -> dict:
    from quant.alpha.weekly import build
    asof = pd.Timestamp(asof) if asof is not None else pd.Timestamp.today().normalize()
    info = update_data(source)
    b = build(end=str(asof.date()), **data_paths(source))
    t = shadow.latest_complete_rebalance(b["w"]["close"].index, asof)
    keep = b["rb"] <= t  # 当月还没走完的“调仓日”不用
    for k in ("fwd", "univ", "up", "dn", "tradable", "mcap"):
        b[k] = b[k].loc[keep]
    b["f"] = {k: v.loc[keep] for k, v in b["f"].items()}
    b["rb"] = b["rb"][keep]
    b["fwd"].loc[t] = float("nan")  # 最后一个调仓日的下期收益还没走完
    shadow_dir = Path(shadow_dir)
    recs = shadow.load_records(shadow_dir)
    recorded = False
    if not any(r["rebalance"] == str(t.date()) for r in recs):
        before = [r for r in recs if r["rebalance"] < str(t.date())]
        shadow.write_record(shadow.make_record(b, t, before[-1] if before else None, source=source), shadow_dir)
        recs, recorded = shadow.load_records(shadow_dir), True
    real = shadow.realized(recs, b["w"]["ret"])
    real.to_csv(shadow_dir / "returns.csv", index=False)
    tg = shadow.targets(b)
    bt = {k: {s: float(b["fwd"].loc[pd.Timestamp(s), sorted(tg[k][pd.Timestamp(s)])].fillna(0.0).mean())
              for s in real.start.unique() if pd.Timestamp(s) in tg[k]} for k in shadow.TRACKED}
    dev = deviation(real, bt)
    ics = {k: fev.ic_series(b["f"][k], b["fwd"], b["univ"]) for k in spec.W_FACTORS}
    cur = next(r for r in recs if r["rebalance"] == str(t.date()))
    prev = [r for r in recs if r["rebalance"] < cur["rebalance"]]
    holdings, p_held = {}, {}
    for r in prev:
        p_held = {k: shadow.held_of(r, k, p_held.get(k, set())) for k in r["portfolios"]}
    for k in cur["portfolios"]:
        h = shadow.held_of(cur, k, p_held.get(k, set()))
        holdings[k] = {"target_n": len(cur["portfolios"][k]), "held_n": len(h),
                       "overlap": (len(h & p_held[k]) / len(h)) if k in p_held and h else None}
    m = {"asof": str(asof.date()), "data": info, "stale_days": int((asof - pd.Timestamp(info["last_week"])).days),
         "rebalance": str(t.date()), "recorded": recorded, "universe_n": cur["universe_n"], "holdings": holdings,
         "realized": real.to_dict("records"), "deviation": dev.to_dict("records"), "ic_alerts": ic_alerts(ics),
         "ic_series": {k: {str(d.date()): float(v) for d, v in s.dropna().items()} for k, s in ics.items()}}
    Path(monitor_json).write_text(json.dumps(m, ensure_ascii=False, indent=1))
    report = Path(report_dir) / f"因子监控-{asof.date()}.md"
    report.write_text(render(m))
    return {"rebalance": m["rebalance"], "recorded": recorded, "realized_periods": int(real[["start", "end"]].drop_duplicates().shape[0]),
            "alerts": [k for k, a in m["ic_alerts"].items() if a["alert"]], "report": str(report)}


def main(argv: list[str] | None = None) -> int:
    import warnings
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=DEFAULT_SOURCE, choices=list(SOURCES))
    ap.add_argument("--asof", default=None, help="按哪一天来判断调仓日是否走完（默认今天）")
    a = ap.parse_args(argv)
    out = run(a.source, a.asof)
    print(f"调仓日 {out['rebalance']}｜观察盘记录{'新写入' if out['recorded'] else '已存在，未覆盖'}｜已走完的持有期 {out['realized_periods']} 个｜"
          f"RankIC 告警 {out['alerts'] or '无'} → {out['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
