"""月度面板与因子值。所有因子在月末 t 只用 t 及以前的信息；方向统一为“值越大，预期下月收益越高”。"""
from pathlib import Path

import numpy as np
import pandas as pd

from quant.factors.data import DIR

MIN_AGE = 252  # 上市满约一年（第一次运行后发现次新股问题而加，报告里注明）

# 因子定义（运行前固定）：名称 → 说明
FACTORS = {
    "EP": "盈利收益率 = 1 / 市盈率TTM（亏损股为负值，保留）",
    "BP": "账面市值比 = 1 / 市净率（净资产为负的剔除）",
    "DY": "股息率 = 近 12 个月已实施现金分红（税前，每股）/ 月末不复权收盘价",
    "LOWVOL": "低波动 = -过去 252 个交易日日收益标准差（至少 120 个有效交易日）",
    "MOM12_1": "12-1 动量 = t-1 月末 / t-12 月末 后复权收盘 - 1（跳过最近一个月）",
    "LOWTURN": "低换手 = -过去 20 个交易日平均换手率",
    "REV1": "1 个月反转 = -(当月收益)",
}


def dividend_ttm(div: pd.DataFrame, month_ends: pd.DatetimeIndex) -> pd.Series:
    """每个月末近 12 个月（不含 12 个月前当天）除权除息的每股税前现金分红；只计“实施”的记录。"""
    out = pd.Series(0.0, index=month_ends)
    if div is None or div.empty or "ex_date" not in div:
        return out
    d = div.dropna(subset=["ex_date", "cash_per10"])
    if "status" in d:
        d = d[d.status.astype(str).str.contains("实施")]
    for t in month_ends:
        m = (d.ex_date <= t) & (d.ex_date > t - pd.DateOffset(years=1))
        out[t] = float(d.loc[m, "cash_per10"].sum()) / 10
    return out


def stock_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    """一只股票的日线 → 月末一行：后复权收盘、最后一个交易日的日期与交易状态、ST、PE、PB、252 日波动、20 日换手、
    累计交易日数（数据起点 2009 年起算，用来剔除次新股）。"""
    d = daily.sort_values("date").set_index("date")
    traded = d.tradestatus == 1
    ret = d.close.where(traded).pct_change(fill_method=None)
    vol = ret.rolling(252, min_periods=120).std()
    turn = d.turn.where(traded)
    turn20 = turn.rolling(20, min_periods=10).mean()
    g = pd.DataFrame({"close": d.close, "status": d.tradestatus, "isST": d.isST, "pe": d.peTTM, "pb": d.pbMRQ,
                      "vol252": vol, "turn20": turn20, "last_date": d.index.to_series(),
                      "age": traded.cumsum().astype(float)}).resample("ME").last()
    return g


def panels(codes: list[str], cache: Path = DIR) -> dict[str, pd.DataFrame]:
    """读缓存，拼成 月末 × 股票 的宽表。"""
    cols = {k: {} for k in ("close", "status", "isST", "pe", "pb", "vol252", "turn20", "last_date", "age", "raw_close", "div_ttm")}
    for c in codes:
        p = cache / "daily" / f"{c}.parquet"
        if not p.exists():
            continue
        m = stock_monthly(pd.read_parquet(p))
        for k in ("close", "status", "isST", "pe", "pb", "vol252", "turn20", "last_date", "age"):
            cols[k][c] = m[k]
        rm = cache / "raw_m" / f"{c}.parquet"
        if rm.exists():
            r = pd.read_parquet(rm).set_index("date").close
            cols["raw_close"][c] = r.resample("ME").last()
        dp = cache / "div" / f"{c}.parquet"
        div = pd.read_parquet(dp) if dp.exists() else None
        cols["div_ttm"][c] = dividend_ttm(div, m.index)
    return {k: pd.DataFrame(v).sort_index() for k, v in cols.items()}


def members_panel(members: pd.DataFrame, index: pd.DatetimeIndex, codes: list[str]) -> pd.DataFrame:
    """月末 t 是否为沪深300 成分（按该月查询到的快照）。"""
    m = members.assign(me=pd.to_datetime(members.month_end) + pd.offsets.MonthEnd(0))
    out = pd.DataFrame(False, index=index, columns=codes)
    for t, g in m.groupby("me"):
        if t in out.index:
            out.loc[t, out.columns.intersection(g.code)] = True
    return out


def universe(member: pd.DataFrame, p: dict[str, pd.DataFrame], market_last: pd.Series) -> pd.DataFrame:
    """可投资股票：当月成分、非 ST、月末最后一个交易日正常交易（停牌的买不进，剔除）、上市满 MIN_AGE 个交易日
    （次新股上市初期的连续一字涨停买不到，不剔除会把这部分收益算进高估值、无分红的组）。"""
    last = p["last_date"].reindex_like(member)
    on_last_day = last.eq(market_last.reindex(member.index), axis=0)
    ok = member & on_last_day & p["status"].reindex_like(member).eq(1) & p["isST"].reindex_like(member).ne(1)
    if "age" in p:
        ok &= p["age"].reindex_like(member).ge(MIN_AGE)
    return ok.fillna(False).astype(bool)


def factor_values(p: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    close = p["close"]
    pb = p["pb"]
    return {
        "EP": 1 / p["pe"].replace(0, np.nan),
        "BP": (1 / pb).where(pb > 0),
        "DY": p["div_ttm"] / p["raw_close"].reindex_like(close),
        "LOWVOL": -p["vol252"],
        "MOM12_1": close.shift(1) / close.shift(12) - 1,
        "LOWTURN": -p["turn20"],
        "REV1": -(close / close.shift(1) - 1),
    }


def forward_return(close: pd.DataFrame) -> pd.DataFrame:
    """t 月末到 t+1 月末的后复权收益；下个月没有价格（如退市）为空。"""
    return close.shift(-1) / close - 1
