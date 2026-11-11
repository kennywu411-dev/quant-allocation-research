"""全 A 股周线下载（baostock，含退市股；周线涨跌幅已按除权除息调整，2026-11-11 抽查 3 只送转股确认）。
单进程、单个登录会话顺序请求；遇到“黑名单”立即停止。python -m quant.alpha.weekly_data [--sleep 0.3]"""
import argparse
import json
import time
from datetime import datetime

import pandas as pd

from quant.alpha import data

WDIR = data.DIR / "weekly"
W_FIELDS = "date,code,close,amount,turn,pctChg"


def fetch(bs, code: str) -> bool:
    out = WDIR / f"{code}.parquet"
    if out.exists():
        return False
    df = data._q(bs.query_history_k_data_plus(code, W_FIELDS, start_date=data.START, end_date=data.END,
                                             frequency="w", adjustflag="3"))
    num = [c for c in W_FIELDS.split(",") if c not in ("date", "code")]
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
    codes = sorted(set(pd.read_csv(data.DIR / "all_members.csv", dtype=str).code))
    t0, failed = time.time(), []
    if bs.login().error_code != "0":
        raise SystemExit("登录失败")
    try:
        for i, c in enumerate(codes, 1):
            for attempt in range(3):
                try:
                    if fetch(bs, c):
                        time.sleep(a.sleep)
                    break
                except data.Blacklisted as e:
                    raise SystemExit(f"被 baostock 拉黑，立即停止：{e}")
                except Exception as e:
                    print("失败", c, type(e).__name__, str(e)[:80], flush=True)
                    time.sleep(10 * (attempt + 1))
            else:
                failed.append(c)
            if i % 250 == 0:
                print(f"周线 {i}/{len(codes)}（{time.time() - t0:.0f} 秒）", flush=True)
    finally:
        bs.logout()
    (WDIR / "meta.json").write_text(json.dumps({"fetched_at": datetime.now().isoformat(timespec="seconds"),
                                                "failed": failed, "fields": W_FIELDS}, ensure_ascii=False, indent=1))
    print(f"完成（{time.time() - t0:.0f} 秒）；失败 {len(failed)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
