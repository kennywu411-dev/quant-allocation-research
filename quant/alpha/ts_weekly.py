"""Tushare 日线 → 因子线的周线缓存（与 baostock 周线同一格式），让月度流水线可以换数据源。
python -m quant.alpha.ts_weekly           由本地 Tushare 缓存（quant/tsdata，另行下载）生成：
    data/cache/alpha/weekly_ts/<代码>.parquet、all_members_ts.csv、stock_basic_ts.csv
python -m quant.alpha.ts_weekly --check   与 baostock 周线交叉核对 → reports/数据源交叉核对-<日期>.md
python -m quant.alpha.ts_weekly --coverage 统计本地 Tushare 缓存的行数与日期范围 → research/tsdata_coverage.json（看板读取）
只做数据转换和核对，不算任何因子收益；不新增试验。"""
import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant.alpha import data
from quant.tsdata import store

W_COLS = ["date", "code", "close", "amount", "turn", "pctChg"]
START = "20130101"


def code_of(ts_code: str) -> str:
    num, ex = ts_code.split(".")
    return f"{ex.lower()}.{num}"


def to_weekly(d: pd.DataFrame) -> pd.DataFrame:
    """d = 日线（ts_code, trade_date, close, amount[千元], pct_chg[%，已按除权调整], turnover_rate[%]）。
    周线：日期 = 周内最后一个交易日，收盘 = 当日收盘，成交额与换手 = 周内合计，涨跌幅 = 周内复利。停牌日没有行。"""
    d = d.sort_values(["ts_code", "trade_date"]).copy()
    d["day"] = pd.to_datetime(d.trade_date, format="%Y%m%d")
    d["wk"] = d.day.dt.to_period("W-FRI")
    d["lg"] = np.log1p(d.pct_chg / 100)
    g = d.groupby(["ts_code", "wk"], sort=True)
    w = pd.DataFrame({"date": g.day.last(), "close": g.close.last(), "amount": g.amount.sum() * 1000.0,
                      "turn": g.turnover_rate.sum(min_count=1), "pctChg": (np.exp(g.lg.sum()) - 1) * 100}).reset_index()
    w["code"] = w.ts_code.map(code_of)
    return w[W_COLS]


def members(basic: pd.DataFrame, month_ends: pd.DatetimeIndex) -> pd.DataFrame:
    """每个月末在市的沪深 A股（已上市、还没退市）；不含北交所，与 baostock 名单口径一致。"""
    b = basic[~basic.ts_code.str.endswith(".BJ")]
    lst = pd.to_datetime(b.list_date, format="%Y%m%d")
    dl = pd.to_datetime(b.delist_date, format="%Y%m%d", errors="coerce")
    codes = b.ts_code.map(code_of)
    rows = [pd.DataFrame({"month_end": str(t.date()), "code": codes[(lst <= t) & (dl.isna() | (dl > t))]}) for t in month_ends]
    return pd.concat(rows, ignore_index=True)


def convert(root: Path = store.ROOT, out: Path = data.DIR, start: str = START) -> dict:
    out = Path(out)
    d = store.load("daily", start=start, columns=["ts_code", "trade_date", "close", "amount", "pct_chg"], root=root)
    tb = store.load("daily_basic", start=start, columns=["ts_code", "trade_date", "turnover_rate"], root=root)
    d = d.merge(tb, on=["ts_code", "trade_date"], how="left")
    d = d[~d.ts_code.str.endswith(".BJ")]
    w = to_weekly(d)
    wdir = out / "weekly_ts"
    wdir.mkdir(parents=True, exist_ok=True)
    for c, g in w.groupby("code", sort=False):
        g.to_parquet(wdir / f"{c}.parquet", index=False)
    days = pd.DatetimeIndex(sorted(pd.to_datetime(d.trade_date.unique(), format="%Y%m%d")))
    me = pd.DatetimeIndex(pd.Series(days, index=days).groupby(days.to_period("M")).max().to_numpy())
    basic = store.load("stock_basic", root=root)
    members(basic, me).to_csv(out / "all_members_ts.csv", index=False)
    b = basic[~basic.ts_code.str.endswith(".BJ")]
    pd.DataFrame({"code": b.ts_code.map(code_of), "ipoDate": pd.to_datetime(b.list_date, format="%Y%m%d").dt.strftime("%Y-%m-%d")}
                 ).to_csv(out / "stock_basic_ts.csv", index=False)
    return {"source": "tushare", "files": int(w.code.nunique()), "last_day": str(days[-1].date()), "last_week": str(w.date.max().date())}


def check(out: Path = data.DIR, end: str = "2026-10-30") -> str:
    """与 baostock 周线逐格对比（重叠区间），并比较最近一个调仓日的股票池和观察盘目标持仓。"""
    import json
    from quant.alpha import shadow
    from quant.alpha.weekly import build, load_weekly, week_end
    mem_b = pd.read_csv(out / "all_members.csv", dtype=str)
    mem_t = pd.read_csv(out / "all_members_ts.csv", dtype=str)
    cb, ct = set(mem_b.code), set(mem_t.code)
    wb = load_weekly(sorted(cb), out / "weekly")
    wt = load_weekly(sorted(ct), out / "weekly_ts")
    idx = wb["close"].index.intersection(wt["close"].index)
    idx = idx[(idx >= "2014-01-01") & (idx <= end)]
    cols = wb["close"].columns.intersection(wt["close"].columns)
    L = [f"# 数据源交叉核对：Tushare 合成周线 对 baostock 周线（{date.today():%Y-%m-%d}）", "",
         "> 研究记录，不是投资建议；作者不是持牌金融顾问；历史回测不代表未来收益。只比数据和持仓重合度，不算任何因子收益，不新增试验。", "",
         "## 覆盖", "",
         f"- 名单里出现过的股票：baostock {len(cb):,} 只，Tushare {len(ct):,} 只，共同 {len(cb & ct):,} 只；只在 baostock {len(cb - ct):,} 只，只在 Tushare {len(ct - cb):,} 只。",
         f"- 对比区间 {idx[0].date()} 至 {idx[-1].date()}，{len(idx)} 周 × {len(cols):,} 只共同股票。", "",
         "## 逐格对比（两边都有成交的周）", "", "| 字段 | 可比格数 | 一致的比例 | 一致的标准 | 差异的中位数 | 99% 分位 |", "|---|---:|---:|---|---:|---:|"]
    both = wb["traded"].loc[idx, cols] & wt["traded"].loc[idx, cols]
    def row(name, a, b, tol, rel, lab):
        a, b = a.loc[idx, cols].where(both), b.loc[idx, cols].where(both)
        diff = pd.Series(((a / b - 1) if rel else (a - b)).abs().to_numpy().ravel()).dropna()
        L.append(f"| {name} | {len(diff):,} | {(diff <= tol).mean():.2%} | {lab} | {diff.median():.4g} | {diff.quantile(0.99):.4g} |")
        return float((diff <= tol).mean())
    row("周涨跌幅（百分点）", wb["pctChg"], wt["pctChg"], 0.05, False, "相差 ≤ 0.05 个百分点")
    row("收盘价", wb["close"], wt["close"], 0.001, True, "相对差 ≤ 0.1%")
    row("周成交额", wb["amount"], wt["amount"], 0.001, True, "相对差 ≤ 0.1%")
    row("周换手率", wb["turn"], wt["turn"], 0.01, True, "相对差 ≤ 1%")
    only_b = (wb["traded"].loc[idx, cols] & ~wt["traded"].loc[idx, cols]).to_numpy().sum()
    only_t = (wt["traded"].loc[idx, cols] & ~wb["traded"].loc[idx, cols]).to_numpy().sum()
    L += ["", f"- 只有一边有成交的周：只在 baostock {int(only_b):,} 格，只在 Tushare {int(only_t):,} 格（共 {int(both.to_numpy().sum()):,} 格两边都有）。", ""]
    bb = build(end=end)
    bt = build(end=end, cache=out / "weekly_ts", members=out / "all_members_ts.csv", basic=out / "stock_basic_ts.csv")
    t = shadow.latest_complete_rebalance(bb["w"]["close"].index, end)
    ub, ut = (set(x["univ"].loc[t][x["univ"].loc[t]].index) for x in (bb, bt))
    L += [f"## 调仓日 {t.date()} 的股票池与观察盘目标持仓", "",
          f"- 股票池：baostock {len(ub):,} 只，Tushare {len(ut):,} 只，共同 {len(ub & ut):,} 只（占 baostock 的 {len(ub & ut) / len(ub):.1%}）。",
          "", "| 组合 | baostock 目标只数 | Tushare 目标只数 | 重合只数 | 重合比例（对 baostock） |", "|---|---:|---:|---:|---:|"]
    tb_, tt_ = shadow.targets(bb), shadow.targets(bt)
    for k in shadow.TRACKED:
        a, b = tb_[k][t], tt_[k][t]
        L.append(f"| {k} | {len(a)} | {len(b)} | {len(a & b)} | {len(a & b) / len(a):.1%} |")
    rec = Path("live/alpha_shadow") / f"{t.date()}.json"
    if rec.exists():
        r = json.loads(rec.read_text())
        L += ["", "- baostock 重算的目标持仓与已记录的观察盘首期：" + "；".join(
            f"{k} 重合 {len(tb_[k][t] & set(r['portfolios'][k]))}/{len(r['portfolios'][k])}" for k in shadow.TRACKED) + "。"]
    L += ["", "## 怎么读", "",
          "- 缓冲带持仓依赖从 2014 年起的全部历史，两个数据源在个别周的小差异会沿路径累积，所以目标持仓不会完全相同。",
          "- 在把流水线默认数据源从 `cache`（baostock）换成 `tushare` 之前，应以这份对比为依据由用户决定；换源那一期要在观察盘记录里写明。",
          "- 没有做的：逐只追查差异原因；日线级别的对比（baostock 日线还在下载）。", "",
          "## 复现", "", "```bash", "PYTHONPATH=. .venv/bin/python -W ignore -m quant.alpha.ts_weekly", "PYTHONPATH=. .venv/bin/python -W ignore -m quant.alpha.ts_weekly --check", "```", ""]
    return "\n".join(L)


DATASETS = {"daily": "日线行情", "adj_factor": "复权因子", "daily_basic": "每日指标（市值、换手、估值）", "stock_st": "每日 ST 名单",
            "income": "利润表", "balancesheet": "资产负债表", "cashflow": "现金流量表", "forecast": "业绩预告"}
STATEMENTS = ("income", "balancesheet", "cashflow")


def coverage(root: Path = store.ROOT) -> dict:
    """本地 Tushare 缓存的覆盖情况：只数行数、日期范围、退市股和公告日缺失，不判断数据对不对。"""
    import pyarrow.parquet as pq
    out = []
    for name, label in DATASETS.items():
        ks = store.keys(name, root)
        if not ks:
            continue
        rows = sum(pq.read_metadata(store.path(name, k, root)).num_rows for k in ks)
        out.append({"name": name, "label": label, "files": len(ks), "rows": int(rows), "first": ks[0][:8], "last": ks[-1][:8]})
    c = {"asof": f"{date.today():%Y-%m-%d}", "datasets": out, "total_rows": int(sum(x["rows"] for x in out))}
    basic = store.load("stock_basic", root=root)
    if len(basic):
        gone = set(basic.ts_code[basic.delist_date.notna()])
        traded = set(store.load("daily", columns=["ts_code"], root=root).ts_code)
        c.update(stocks=int(basic.ts_code.nunique()), delisted=len(gone), daily_stocks=len(traded), delisted_with_daily=len(gone & traded))
    st = [store.load(n, columns=["ann_date", "f_ann_date"], root=root) for n in STATEMENTS if store.keys(n, root)]
    if st:
        st = pd.concat(st, ignore_index=True)
        c.update(statement_rows=int(len(st)), ann_date_missing=int(st.ann_date.isna().sum()), f_ann_date_missing=int(st.f_ann_date.isna().sum()))
    return c


def main(argv: list[str] | None = None) -> int:
    import warnings
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--coverage", action="store_true")
    a = ap.parse_args(argv)
    if a.coverage:
        import json
        p = Path("research/tsdata_coverage.json")
        p.write_text(json.dumps(coverage(), ensure_ascii=False, indent=1))
        print("→", p)
    elif a.check:
        p = Path("reports") / f"数据源交叉核对-{date.today():%Y-%m-%d}.md"
        p.write_text(check())
        print("→", p)
    else:
        print(convert())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
