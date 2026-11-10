"""因子检验数据的备用下载路径：股票池用“今天的沪深300 成分股”（baostock 历史成分取不到时使用）。
局限（报告里必须写明）：只包含活到今天、且今天在指数里的公司 → 幸存者偏差；动量、低波这类“过去表现好”的因子会被高估。
来源（全部免费，akshare）：
- 当前成分：中证指数官网 index_stock_cons_csindex("000300")；
- 后复权日线（收盘、成交额、换手率）：新浪 stock_zh_a_daily(adjust="hfq")；停牌日没有行；
- 不复权日线 → 月末收盘（股息率分母）：新浪 stock_zh_a_daily(adjust="")；
（东方财富接口检验时被限流，未使用。）
- 市盈率TTM、市净率：百度 stock_zh_valuation_baidu(period="全部")，约每 22 天一个点，按日期向后对齐（最多滞后 22 天）；
- 现金分红：与主路径相同，data.download_dividends（新浪）。
输出格式与 baostock 路径一致（daily/ raw_m/ div/），calc.panels 直接可读。
python -m quant.factors.data_current [--sleep 0.8]；已下载的跳过，中断后重跑接着下。单线程，避免再被数据源限流。"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from quant.factors import data as base

DIR = Path("data/cache/factors_current")
MEMBERS = DIR / "hs300_members_current.csv"


def to_code(sym: str, exchange: str) -> str:
    """'600000' + '上海证券交易所' → 'sh.600000'（与 baostock 代码格式一致）。"""
    return ("sh." if "上海" in exchange else "sz.") + sym


def current_members(path: Path = MEMBERS) -> pd.DataFrame:
    """今天的成分股，展开到每个月末（同一份名单），列与历史成分文件相同：month_end, update_date, code。"""
    if path.exists():
        return pd.read_csv(path, dtype=str)
    import akshare as ak
    df = ak.index_stock_cons_csindex(symbol="000300")
    codes = sorted(to_code(str(s).zfill(6), e) for s, e in zip(df["成分券代码"], df["交易所"]))
    asof = str(df["日期"].iloc[0])[:10]
    rows = [{"month_end": f"{d:%Y-%m-%d}", "update_date": asof, "code": c} for d in base.month_ends() for c in codes]
    out = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return out


def build_daily(px: pd.DataFrame, pe: pd.DataFrame, pb: pd.DataFrame, code: str) -> pd.DataFrame:
    """新浪日线 + 百度估值（按日期向后对齐）→ 与 baostock 日线相同的列（换手率换成百分比）。有行即正常交易，ST 标记取不到记 0。"""
    d = pd.DataFrame({"date": pd.to_datetime(px["date"]), "code": code, "close": px["close"].astype(float),
                      "amount": px["amount"].astype(float), "turn": px["turnover"].astype(float) * 100}).sort_values("date")
    d["tradestatus"], d["isST"] = 1.0, 0.0
    for name, v in (("peTTM", pe), ("pbMRQ", pb)):
        v = pd.DataFrame({"date": pd.to_datetime(v["date"]), name: pd.to_numeric(v["value"], errors="coerce")})
        d = pd.merge_asof(d, v.sort_values("date"), on="date", direction="backward")
    return d.reset_index(drop=True)


def fetch_stock(code: str, sleep: float, cache: Path = DIR) -> None:
    import akshare as ak
    sym, sina = code.split(".")[1], code.replace(".", "")
    s, e = base.DAILY_START.replace("-", ""), base.END.replace("-", "")
    out_d, out_m = cache / "daily" / f"{code}.parquet", cache / "raw_m" / f"{code}.parquet"
    if not out_d.exists():
        px = base._retry(lambda: ak.stock_zh_a_daily(symbol=sina, start_date=s, end_date=e, adjust="hfq"))
        time.sleep(sleep)
        pe = base._retry(lambda: ak.stock_zh_valuation_baidu(symbol=sym, indicator="市盈率(TTM)", period="全部"))
        time.sleep(sleep)
        pb = base._retry(lambda: ak.stock_zh_valuation_baidu(symbol=sym, indicator="市净率", period="全部"))
        time.sleep(sleep)
        out_d.parent.mkdir(parents=True, exist_ok=True)
        build_daily(px, pe, pb, code).to_parquet(out_d, index=False)
    if not out_m.exists():
        raw = base._retry(lambda: ak.stock_zh_a_daily(symbol=sina, start_date=s, end_date=e, adjust=""))
        time.sleep(sleep)
        raw = pd.DataFrame({"date": pd.to_datetime(raw["date"]), "close": raw["close"].astype(float)}).set_index("date")
        m = raw.close.groupby(raw.index.to_period("M")).agg(lambda x: x.iloc[-1])  # 每月最后一个交易日的收盘
        dates = raw.index.to_series().groupby(raw.index.to_period("M")).max()
        out_m.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"date": dates.values, "code": code, "close": m.values}).to_parquet(out_m, index=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.8)
    a = ap.parse_args(argv)
    t0 = time.time()
    codes = sorted(set(current_members().code))
    print(f"当前成分 {len(codes)} 只", flush=True)
    failed = []
    for i, c in enumerate(codes, 1):
        try:
            fetch_stock(c, a.sleep)
        except Exception as ex:
            failed.append(c)
            print("失败", c, type(ex).__name__, str(ex)[:120], flush=True)
        if i % 25 == 0:
            print(f"行情 {i}/{len(codes)}（{time.time() - t0:.0f} 秒）", flush=True)
    base.DIR, saved = DIR, base.DIR  # 分红写到同一缓存目录
    try:
        div_failed = base.download_dividends(codes)
    finally:
        base.DIR = saved
    meta = {"fetched_at": datetime.now().isoformat(timespec="seconds"), "start": base.START, "end": base.END,
            "universe": "当前沪深300 成分（有幸存者偏差）", "n_codes": len(codes), "failed_kline": failed,
            "failed_div": div_failed,
            "sources": {"members": "akshare index_stock_cons_csindex", "daily": "新浪 后复权日线",
                        "valuation": "百度 PE TTM / PB（约 22 天一个点）", "raw_m": "新浪 不复权日线取月末",
                        "div": "akshare stock_history_dividend_detail"}}
    (DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"完成（{time.time() - t0:.0f} 秒）；行情失败 {len(failed)}，分红失败 {len(div_failed)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
