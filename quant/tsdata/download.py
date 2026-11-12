"""Tushare 全市场下载器：缓存到 data/cache/tushare/<接口>/，可断点续传（已有的分片跳过），限速可配。

  source ~/.zshrc && .venv/bin/python -m quant.tsdata.download [--start 20100101] [--end YYYYMMDD]
      [--only daily,adj_factor,...] [--rate 300] [--workers 6] [--refresh-days 550] [--force]

数据集（--only 用这些名字）：
  stock_basic   股票列表（上市 + 退市 + 暂停上市，含 delist_date）       键 all
  trade_cal     上交所交易日历                                           键 SSE
  daily / adj_factor / daily_basic / stock_st   每个交易日一个分片       键 YYYYMMDD
  income / balancesheet / cashflow   每个报告期 × report_type(1/4/5) 一个分片（用 *_vip 接口）  键 YYYYMMDD_rt1
  forecast      每个报告期一个分片（forecast_vip）                       键 YYYYMMDD
没有权限的接口整类跳过并写进 meta.json；最近的报告期会被重新拉取（新公告和更正会改变内容）。"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from quant.tsdata import store
from quant.tsdata.client import Client, NoPermission

BY_DATE = ("daily", "adj_factor", "daily_basic", "stock_st")
STATEMENTS = {"income": "income_vip", "balancesheet": "balancesheet_vip", "cashflow": "cashflow_vip"}
REPORT_TYPES = ("1", "4", "5")  # 1 合并报表（最新）；4 调整合并报表（上年同期调整数）；5 调整前合并报表（原始披露值）
ALL = ("stock_basic", "trade_cal", *BY_DATE, *STATEMENTS, "forecast")
FIN_START_YEAR = 2009
EMPTY_GRACE_DAYS = 7      # 最近几天的空结果不落盘：数据可能只是还没发布
REFRESH_MIN_AGE_H = 20    # 需要刷新的报告期分片，距上次写入不足这么多小时就不重复拉


def periods(start_year: int, today: date) -> list[str]:
    """从 start_year 一季度到 today 之前（含当天）最近一个季度末的全部报告期。"""
    out = []
    for y in range(start_year, today.year + 1):
        for md in ("0331", "0630", "0930", "1231"):
            p = f"{y}{md}"
            if p <= f"{today:%Y%m%d}":
                out.append(p)
    return out


def _stale(p: Path, now: float) -> bool:
    return now - p.stat().st_mtime > REFRESH_MIN_AGE_H * 3600


def plan(names: list[str], trade_dates: list[str], today: date, refresh_days: int, root: Path = store.ROOT,
         now: float | None = None, force: bool = False) -> dict[str, list[tuple[str, str, dict]]]:
    """列出还要下载的任务：{数据集: [(键, 接口名, 参数)]}。已有分片跳过；近 refresh_days 天内的报告期若分片已旧则重拉。
    force=True 时不看已有分片，全部重拉并覆盖。"""
    now = time.time() if now is None else now
    cutoff = f"{today - timedelta(days=refresh_days):%Y%m%d}"
    jobs: dict[str, list[tuple[str, str, dict]]] = {}
    for n in names:
        js = []
        if n in BY_DATE:
            js = [(d, n, {"trade_date": d}) for d in trade_dates if force or not store.exists(n, d, root)]
        elif n in STATEMENTS or n == "forecast":
            for p in periods(FIN_START_YEAR, today):
                for rt in (REPORT_TYPES if n in STATEMENTS else (None,)):
                    key = f"{p}_rt{rt}" if rt else p
                    f = store.path(n, key, root)
                    if not force and f.exists() and not (p >= cutoff and _stale(f, now)):
                        continue
                    params = {"period": p, **({"report_type": rt} if rt else {})}
                    js.append((key, STATEMENTS.get(n, "forecast_vip"), params))
        jobs[n] = js
    return jobs


def fetch_static(client: Client, name: str, start: str, end: str, root: Path = store.ROOT) -> pd.DataFrame:
    if name == "stock_basic":
        fields = "ts_code,symbol,name,area,industry,market,exchange,list_status,list_date,delist_date,is_hs"
        df = pd.concat([client.fetch("stock_basic", list_status=s, fields=fields) for s in "LDP"], ignore_index=True)
        store.write("stock_basic", "all", df, root)
    else:
        df = client.fetch("trade_cal", exchange="SSE", start_date=start, end_date=end)
        df = df.sort_values("cal_date", ignore_index=True)
        store.write("trade_cal", "SSE", df, root)
    return df


def run_jobs(client: Client, name: str, jobs: list[tuple[str, str, dict]], workers: int, today: date,
             root: Path = store.ROOT, log=print) -> dict:
    """并发执行一类数据的任务。返回 {done, empty_skipped, failed, no_permission}。"""
    res = {"done": 0, "empty_skipped": [], "failed": [], "no_permission": None}
    grace = f"{today - timedelta(days=EMPTY_GRACE_DAYS):%Y%m%d}"
    if not jobs:
        return res
    # 先单独跑第一个：没权限就整类跳过，不浪费后面的调用
    t0 = time.time()

    def one(job):
        key, api, params = job
        df = client.fetch(api, exhaustive=api.endswith("_vip"), **params)
        if df.empty and key[:8] >= grace:
            return key, None
        store.write(name, key, df, root)
        return key, len(df)

    def record(job, fut_result=None, err=None):
        if err is not None:
            res["failed"].append({"key": job[0], "error": str(err)[:160]})
        elif fut_result[1] is None:
            res["empty_skipped"].append(fut_result[0])
        else:
            res["done"] += 1

    try:
        record(jobs[0], one(jobs[0]))
    except NoPermission as e:
        res["no_permission"] = str(e)
        return res
    except Exception as e:  # noqa: BLE001
        record(jobs[0], err=e)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(one, j): j for j in jobs[1:]}
        for i, f in enumerate(as_completed(futs), 2):
            try:
                record(futs[f], f.result())
            except Exception as e:  # noqa: BLE001
                record(futs[f], err=e)
            if i % 200 == 0:
                log(f"{name} {i}/{len(jobs)}（{time.time() - t0:.0f} 秒）")
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="20100101")
    ap.add_argument("--end", default=f"{date.today():%Y%m%d}")
    ap.add_argument("--only", default=",".join(ALL))
    ap.add_argument("--rate", type=float, default=300, help="每分钟最多调用次数")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--refresh-days", type=int, default=550, help="报告期末在这么多天以内的财务分片会重新拉取")
    ap.add_argument("--force", action="store_true", help="忽略已有分片，把 --only 指定的数据集全部重拉并覆盖")
    a = ap.parse_args(argv)
    names = [n for n in a.only.split(",") if n]
    bad = [n for n in names if n not in ALL]
    if bad:
        raise SystemExit(f"未知数据集：{bad}；可选 {ALL}")
    today = date.today()
    client = Client(per_minute=a.rate)
    t0 = time.time()
    log = lambda s: print(s, flush=True)  # noqa: E731
    if "stock_basic" in names:
        log(f"stock_basic {len(fetch_static(client, 'stock_basic', a.start, a.end))} 行")
    cal = fetch_static(client, "trade_cal", a.start, a.end)
    trade_dates = sorted(cal.loc[cal.is_open.astype(int) == 1, "cal_date"])
    log(f"交易日 {len(trade_dates)} 个（{trade_dates[0]}–{trade_dates[-1]}）")
    todo = plan([n for n in names if n not in ("stock_basic", "trade_cal")], trade_dates, today, a.refresh_days,
                force=a.force)
    summary = {}
    for n, jobs in todo.items():
        log(f"{n}: 待下载 {len(jobs)} 个分片")
        r = run_jobs(client, n, jobs, a.workers, today, log=log)
        summary[n] = {**r, "planned": len(jobs), "files": len(store.keys(n))}
        if r["no_permission"]:
            log(f"{n}: 无权限，跳过（{r['no_permission']}）")
        else:
            log(f"{n}: 完成 {r['done']}，空结果未落盘 {len(r['empty_skipped'])}，失败 {len(r['failed'])}（累计 {time.time() - t0:.0f} 秒）")
    meta_p = store.ROOT / "meta.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    meta.update({"fetched_at": datetime.now().isoformat(timespec="seconds"), "source": "Tushare Pro",
                 "start": a.start, "end": a.end, "datasets": {**meta.get("datasets", {}), **summary}})
    store.ROOT.mkdir(parents=True, exist_ok=True)
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    log(f"全部结束（{time.time() - t0:.0f} 秒，调用 {client.calls} 次）")
    return 1 if any(s["failed"] for s in summary.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
