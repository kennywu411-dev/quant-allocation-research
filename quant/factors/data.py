"""因子检验的数据下载（全部免费源，可复现）：
- 沪深300 历史成分：baostock query_hs300_stocks(date)，每个月末取一次（约每周一个快照，含已退市股票）；
- 个股后复权日线（收盘、成交额、换手率、PE TTM、PB、交易状态、ST）：baostock query_history_k_data_plus，adjustflag=1；
- 个股不复权月末收盘（算股息率的分母）：baostock 月线，adjustflag=3；
- 现金分红明细（每 10 股派息、除权除息日）：akshare stock_history_dividend_detail。
python -m quant.factors.data [--workers 6]；已下载的文件跳过，中断后重跑会接着下。"""
import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd

DIR = Path("data/cache/factors")
START, END = "2010-01-01", "2026-10-31"  # 检验区间（月末）
DAILY_START = "2009-01-01"  # 留出 12 个月给动量和波动率
DAILY_FIELDS = "date,code,close,amount,turn,tradestatus,peTTM,pbMRQ,isST"


def _q(rs) -> pd.DataFrame:
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    if rs.error_code != "0":
        raise RuntimeError(f"baostock {rs.error_code}: {rs.error_msg}")
    return pd.DataFrame(rows, columns=rs.fields)


def _retry(fn, tries: int = 3, wait: float = 5.0):
    for i in range(tries):
        try:
            return fn()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(wait * (i + 1))


def month_ends(start: str = START, end: str = END) -> list[pd.Timestamp]:
    return list(pd.date_range(start, end, freq="BME"))


def download_members(path: Path = DIR / "hs300_members.csv") -> pd.DataFrame:
    """每个月末（工作日）的沪深300 成分；接着已有文件续下。"""
    import baostock as bs
    done = pd.read_csv(path, dtype=str) if path.exists() else pd.DataFrame(columns=["month_end", "update_date", "code"])
    have = set(done.month_end)
    bs.login()
    try:
        parts = [done]
        for d in month_ends():
            key = f"{d:%Y-%m-%d}"
            if key in have:
                continue
            df = _retry(lambda: _q(bs.query_hs300_stocks(date=key)))
            if df.empty:
                raise RuntimeError(f"{key}：沪深300 成分为空")
            parts.append(pd.DataFrame({"month_end": key, "update_date": df.updateDate, "code": df.code}))
            path.parent.mkdir(parents=True, exist_ok=True)
            pd.concat(parts, ignore_index=True).to_csv(path, index=False)
    finally:
        bs.logout()
    return pd.read_csv(path, dtype=str)


def _login():
    import baostock as bs
    bs.login()


def _fetch_stock(code: str) -> str:
    """一只股票的后复权日线 + 不复权月线，各存一个 parquet。"""
    import baostock as bs
    out_d, out_m = DIR / "daily" / f"{code}.parquet", DIR / "raw_m" / f"{code}.parquet"
    if not out_d.exists():
        df = _retry(lambda: _q(bs.query_history_k_data_plus(code, DAILY_FIELDS, start_date=DAILY_START, end_date=END,
                                                            frequency="d", adjustflag="1")))
        num = [c for c in DAILY_FIELDS.split(",") if c not in ("date", "code")]
        df[num] = df[num].replace("", None).astype(float)  # 停牌日成交量、换手率是空串
        df["date"] = pd.to_datetime(df.date)
        out_d.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_d, index=False)
    if not out_m.exists():
        m = _retry(lambda: _q(bs.query_history_k_data_plus(code, "date,code,close", start_date=DAILY_START, end_date=END,
                                                           frequency="m", adjustflag="3")))
        m["close"] = m.close.replace("", None).astype(float)
        m["date"] = pd.to_datetime(m.date)
        out_m.parent.mkdir(parents=True, exist_ok=True)
        m.to_parquet(out_m, index=False)
    return code


def download_dividends(codes: list[str], sleep: float = 0.5) -> list[str]:
    """现金分红明细（akshare，新浪源）；没有分红记录的股票存空表。返回失败的代码。"""
    import akshare as ak
    failed = []
    for code in codes:
        out = DIR / "div" / f"{code}.parquet"
        if out.exists():
            continue
        try:
            df = _retry(lambda: ak.stock_history_dividend_detail(symbol=code.split(".")[1], indicator="分红"))
            time.sleep(sleep)
        except Exception:
            failed.append(code)
            continue
        df = pd.DataFrame(df) if df is not None else pd.DataFrame()
        keep = {"公告日期": "announce", "派息": "cash_per10", "除权除息日": "ex_date", "进度": "status"}
        df = df[[c for c in keep if c in df.columns]].rename(columns=keep)
        for c in ("announce", "ex_date"):
            if c in df:
                df[c] = pd.to_datetime(df[c], errors="coerce")
        if "cash_per10" in df:
            df["cash_per10"] = pd.to_numeric(df.cash_per10, errors="coerce")
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)
    return failed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)
    t0 = time.time()
    mem = download_members()
    codes = sorted(set(mem.code))
    print(f"成分月份 {mem.month_end.nunique()} 个，并集 {len(codes)} 只（{time.time() - t0:.0f} 秒）", flush=True)
    failed = []
    with ProcessPoolExecutor(a.workers, initializer=_login) as ex:
        futs = {ex.submit(_fetch_stock, c): c for c in codes}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                f.result()
            except Exception as e:
                failed.append(futs[f])
                print("失败", futs[f], e, flush=True)
            if i % 50 == 0:
                print(f"行情 {i}/{len(codes)}（{time.time() - t0:.0f} 秒）", flush=True)
    div_failed = download_dividends(codes)
    meta = {"fetched_at": datetime.now().isoformat(timespec="seconds"), "start": START, "end": END,
            "n_codes": len(codes), "failed_kline": failed, "failed_div": div_failed,
            "sources": {"members": "baostock query_hs300_stocks", "daily": "baostock 后复权日线",
                        "raw_m": "baostock 不复权月线", "div": "akshare stock_history_dividend_detail"}}
    (DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"完成（{time.time() - t0:.0f} 秒）；行情失败 {len(failed)}，分红失败 {len(div_failed)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
