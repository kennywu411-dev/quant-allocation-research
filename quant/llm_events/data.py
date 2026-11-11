"""公告标题下载（巨潮资讯，akshare stock_zh_a_disclosure_report_cninfo，免费、可复现）。
- 股票池：与因子检验相同的“当前沪深300 成分股”（data/cache/factors_current/hs300_members_current.csv），有幸存者偏差；
- 字段：代码、标题、公告日期（巨潮只给到日，没有时分）、链接，加标题+链接的 sha1 作为唯一编号；原文不下载；
- 单线程、每只股票之间停顿，已下载的跳过，中断后重跑接着下。
python -m quant.llm_events.data [--start 20200101 --end 20261031 --sleep 6 --pause 600]"""
import argparse
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

DIR = Path("data/cache/llm_events")
MEMBERS = Path("data/cache/factors_current/hs300_members_current.csv")


def ann_id(title: str, url: str) -> str:
    return hashlib.sha1(f"{title}|{url}".encode()).hexdigest()[:16]


def tidy(raw: pd.DataFrame, code: str) -> pd.DataFrame:
    """巨潮原始表 → code, date, title, url, id；去重，按日期排序。"""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["code", "date", "title", "url", "id"])
    d = pd.DataFrame({"code": code, "date": pd.to_datetime(raw["公告时间"]).dt.normalize(),
                      "title": raw["公告标题"].astype(str).str.strip(), "url": raw["公告链接"].astype(str)})
    d["id"] = [ann_id(t, u) for t, u in zip(d.title, d.url)]
    return d.drop_duplicates("id").sort_values(["date", "id"]).reset_index(drop=True)


def fetch(code: str, start: str, end: str, cache: Path = DIR) -> int:
    import akshare as ak
    out = cache / "ann" / f"{code}.parquet"
    if out.exists():
        return -1
    raw = ak.stock_zh_a_disclosure_report_cninfo(symbol=code.split(".")[1], market="沪深京", category="",
                                                  start_date=start, end_date=end)
    d = tidy(raw, code)
    out.parent.mkdir(parents=True, exist_ok=True)
    d.to_parquet(out, index=False)
    return len(d)


def load_all(cache: Path = DIR) -> pd.DataFrame:
    fs = sorted((cache / "ann").glob("*.parquet"))
    return pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True) if fs else tidy(None, "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20200101")
    ap.add_argument("--end", default="20261031")
    ap.add_argument("--sleep", type=float, default=6.0)
    ap.add_argument("--pause", type=float, default=600.0)
    a = ap.parse_args(argv)
    codes = sorted(set(pd.read_csv(MEMBERS, dtype=str).code))
    t0, failed, n, streak = time.time(), [], 0, 0
    for i, c in enumerate(codes, 1):
        for attempt in range(3):  # 连续失败 = 被限流：暂停 a.pause 秒后重试同一只，最多 3 轮
            try:
                k = fetch(c, a.start, a.end)
                streak = 0
                if k >= 0:
                    n += k
                    time.sleep(a.sleep)
                break
            except Exception as e:
                streak += 1
                print("失败", c, type(e).__name__, str(e)[:100], flush=True)
                if streak >= 3:
                    print(f"连续失败 {streak} 次，暂停 {a.pause} 秒", flush=True)
                    time.sleep(a.pause)
                else:
                    time.sleep(a.sleep * 4)
        else:
            failed.append(c)
        if i % 25 == 0:
            print(f"公告 {i}/{len(codes)}，本次新增 {n} 条（{time.time() - t0:.0f} 秒）", flush=True)
    meta = {"fetched_at": datetime.now().isoformat(timespec="seconds"), "start": a.start, "end": a.end,
            "n_codes": len(codes), "failed": failed, "source": "巨潮资讯 akshare stock_zh_a_disclosure_report_cninfo",
            "note": "公告时间只到日，没有时分；只存标题、链接和哈希"}
    (DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"完成（{time.time() - t0:.0f} 秒）；失败 {len(failed)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
