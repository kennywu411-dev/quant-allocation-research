"""全 A 股数据（baostock，免费、含退市股）：
- 证券基本信息（含退市股的上市日、退市日）：query_stock_basic → 推出每个月末在市的 A股（沪 600/601/603/605/688，深 000/001/002/003/300/301）；
- 每只股票不复权日线：开高低收、昨收、成交量、成交额、换手率、交易状态、涨跌幅、PE TTM、PB、ST 标记。
  收益用涨跌幅 pctChg（baostock 按除权除息调整过昨收），流通市值 = 收盘价 × 成交量 / (换手率 / 100)。
上次多进程探测被 baostock 拉黑过：这里只用一个进程、一个登录会话顺序请求，每次之间停顿；遇到“黑名单”立即停止。
python -m quant.alpha.data [--sleep 0.3]；已下载的跳过，可续跑。"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

DIR = Path("data/cache/alpha")
START, END = "2013-01-01", "2026-10-31"
FIELDS = "date,code,open,high,low,close,preclose,volume,amount,turn,tradestatus,pctChg,peTTM,pbMRQ,isST"
A_PREFIX = ("sh.600", "sh.601", "sh.603", "sh.605", "sh.688", "sz.000", "sz.001", "sz.002", "sz.003", "sz.300", "sz.301")


class Blacklisted(RuntimeError):
    pass


def _q(rs) -> pd.DataFrame:
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    if rs.error_code != "0":
        if "黑名单" in rs.error_msg:
            raise Blacklisted(rs.error_msg)
        raise RuntimeError(f"baostock {rs.error_code}: {rs.error_msg}")
    return pd.DataFrame(rows, columns=rs.fields)


def is_a_share(code: str) -> bool:
    return code.startswith(A_PREFIX)


def month_ends() -> list[pd.Timestamp]:
    return list(pd.date_range("2014-01-01", END, freq="BME"))


def members_from_basic(b: pd.DataFrame) -> pd.DataFrame:
    """由证券基本信息（含退市股）推出每个月末在市的 A股：上市日 ≤ 月末，且（没有退市日 或 退市日 > 月末）。
    比逐月调用 query_all_stock 快得多（1 次请求 vs 154 次）；当天停不停牌由日线的交易状态判断。"""
    b = b[(b["type"] == "1") & b.code.map(is_a_share)].copy()
    ipo = pd.to_datetime(b.ipoDate, errors="coerce")
    out = pd.to_datetime(b.outDate.replace("", None), errors="coerce")
    rows = []
    for me in month_ends():
        ok = (ipo <= me) & (out.isna() | (out > me))
        rows.append(pd.DataFrame({"month_end": f"{me:%Y-%m-%d}", "code": b.code[ok]}))
    return pd.concat(rows, ignore_index=True)


def basic(bs, path: Path = DIR / "stock_basic.csv") -> pd.DataFrame:
    if not path.exists():
        df = _q(bs.query_stock_basic())
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
    return pd.read_csv(path, dtype=str)


def fetch(bs, code: str, cache: Path = DIR) -> bool:
    out = cache / "daily" / f"{code}.parquet"
    if out.exists():
        return False
    df = _q(bs.query_history_k_data_plus(code, FIELDS, start_date=START, end_date=END, frequency="d", adjustflag="3"))
    num = [c for c in FIELDS.split(",") if c not in ("date", "code")]
    df[num] = df[num].replace("", None).astype(float)
    df["date"] = pd.to_datetime(df.date)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return True


def main(argv: list[str] | None = None) -> int:
    import baostock as bs
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.3)
    a = ap.parse_args(argv)
    t0 = time.time()
    lg = bs.login()
    if lg.error_code != "0":
        raise SystemExit(f"登录失败：{lg.error_msg}")
    failed = []
    try:
        mem = members_from_basic(basic(bs))
        mem.to_csv(DIR / "all_members.csv", index=False)
        codes = sorted(set(mem.code))
        print(f"月末 {mem.month_end.nunique()} 个，A股并集 {len(codes)} 只（{time.time() - t0:.0f} 秒）", flush=True)
        for i, c in enumerate(codes, 1):
            for attempt in range(3):
                try:
                    if fetch(bs, c):
                        time.sleep(a.sleep)
                    break
                except Blacklisted as e:
                    raise SystemExit(f"被 baostock 拉黑，立即停止：{e}")
                except Exception as e:
                    print("失败", c, type(e).__name__, str(e)[:80], flush=True)
                    time.sleep(10 * (attempt + 1))
            else:
                failed.append(c)
            if i % 200 == 0:
                print(f"行情 {i}/{len(codes)}（{time.time() - t0:.0f} 秒）", flush=True)
    finally:
        bs.logout()
    (DIR / "meta.json").write_text(json.dumps({"fetched_at": datetime.now().isoformat(timespec="seconds"), "start": START,
                                               "end": END, "failed": failed, "source": "baostock（含退市股）"},
                                              ensure_ascii=False, indent=1))
    print(f"完成（{time.time() - t0:.0f} 秒）；失败 {len(failed)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
