"""日线宽表 → 月末因子、股票池、下月收益、涨跌停标记。所有月末 t 的量只用 t 及以前的数据。"""
from pathlib import Path

import numpy as np
import pandas as pd

from quant.alpha import data, spec

COLS = ["close", "preclose", "volume", "amount", "turn", "tradestatus", "pctChg", "peTTM", "pbMRQ", "isST"]


def load_daily(codes: list[str], cache: Path = data.DIR) -> dict[str, pd.DataFrame]:
    """读全部日线，拼成 日期 × 股票 的宽表（float32 省内存）。"""
    parts = {c: {} for c in COLS}
    for code in codes:
        p = cache / "daily" / f"{code}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p).set_index("date")
        for c in COLS:
            parts[c][code] = d[c].astype("float32")
    return {c: pd.DataFrame(v).sort_index() for c, v in parts.items()}


def limit_pct(codes: pd.Index, dates: pd.DatetimeIndex, st: pd.DataFrame) -> pd.DataFrame:
    """每只股票每天的涨跌幅限制：主板 10%，ST 5%，科创板 20%，创业板 2020-08-24 起 20%（之前 10%）。"""
    lim = pd.DataFrame(0.10, index=dates, columns=codes, dtype="float32")
    star = [c for c in codes if c.startswith("sh.688")]
    gem = [c for c in codes if c.startswith(("sz.300", "sz.301"))]
    lim[star] = 0.20
    lim.loc[dates >= pd.Timestamp("2020-08-24"), gem] = 0.20
    is_st = st.reindex(index=dates, columns=codes).fillna(0) == 1
    return lim.mask(is_st & (lim == 0.10), 0.05)


def limit_flags(p: dict, lim: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """收盘涨停 / 跌停：收盘价达到（四舍五入到分的）涨停价 / 跌停价。"""
    up_px = (p["preclose"] * (1 + lim)).round(2)
    dn_px = (p["preclose"] * (1 - lim)).round(2)
    traded = p["tradestatus"] == 1
    return (p["close"] >= up_px - 0.001) & traded, (p["close"] <= dn_px + 0.001) & traded


def daily_returns(p: dict) -> pd.DataFrame:
    """日收益 = 涨跌幅 / 100（baostock 的昨收已按除权除息调整）；停牌日为 NaN。"""
    return (p["pctChg"] / 100).where(p["tradestatus"] == 1)


def float_mcap(p: dict) -> pd.DataFrame:
    """流通市值 = 收盘价 × 成交量 / 换手率（换手率以 % 计）；没有成交的日子沿用最近 20 天内的值。"""
    t = p["turn"].where(p["turn"] > 0)
    return (p["close"] * p["volume"] / (t / 100)).ffill(limit=20)


def month_end_dates(dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(dates, index=dates)
    return pd.DatetimeIndex(s.groupby(dates.to_period("M")).max().to_numpy())


def factors(p: dict, ret: pd.DataFrame, mcap: pd.DataFrame, me: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    """12 个候选因子在月末的值（定义见 spec.FACTORS）。"""
    r0 = ret.fillna(0.0)
    lg = np.log1p(r0)
    cum = lambda n: np.exp(lg.rolling(n).sum()) - 1
    mkt = ret.mean(axis=1)
    var_m = mkt.rolling(21, min_periods=15).var()
    cov = ret.rolling(21, min_periods=15).cov(mkt)
    var_r = ret.rolling(21, min_periods=15).var()
    resid = (var_r - cov.pow(2).div(var_m, axis=0)).clip(lower=0)
    illiq = (ret.abs() / p["amount"].where(p["amount"] > 0)).rolling(21, min_periods=15).mean()
    mlog = lg.groupby(lg.index.to_period("M")).sum()  # 月度对数收益，按自然月
    mom = np.exp(mlog.rolling(11).sum().shift(1)) - 1   # 第 t-11 到 t-1 个月，跳过当月
    pe, pb = p["peTTM"], p["pbMRQ"]
    out = {
        "EP": 1 / pe.where(pe != 0),
        "BP": (1 / pb).where(pb > 0),
        "LOWVOL": -ret.rolling(252, min_periods=120).std(),
        "LOWTURN": -p["turn"].where(p["tradestatus"] == 1).rolling(20, min_periods=10).mean(),
        "REV21": -cum(21),
        "SIZE": -np.log(mcap),
        "IVOL": -np.sqrt(resid),
        "ILLIQ": np.log(illiq.where(illiq > 0)),
        "REV5": -cum(5),
        "REV10": -cum(10),
        "MAX": -ret.rolling(21, min_periods=15).max(),
    }
    res = {k: v.reindex(me) for k, v in out.items()}
    res["MOM12_1"] = _align_monthly(mom, me)
    return {k: res[k] for k in spec.FACTORS}


def _align_monthly(m: pd.DataFrame, me: pd.DatetimeIndex) -> pd.DataFrame:
    """日历月末索引 → 当月最后交易日索引。"""
    out = m.reindex(me.to_period("M"))
    out.index = me
    return out


def forward_returns(ret: pd.DataFrame, me: pd.DatetimeIndex) -> pd.DataFrame:
    """月末 t 到下一个月末的收益（复利）；期间停牌日记 0，退市后记 0（按最后成交价拿回现金，略偏乐观）。"""
    r0 = ret.fillna(0.0)
    lr = np.log1p(r0).cumsum()
    at = lr.reindex(me)
    fwd = np.exp(at.shift(-1) - at) - 1
    alive = ret.notna().cumsum().reindex(me)  # 到 t 为止有过交易
    return fwd.where(alive > 0)


def universe(members: pd.DataFrame, p: dict, mcap: pd.DataFrame, me: pd.DatetimeIndex, basic: pd.DataFrame) -> pd.DataFrame:
    """月末可投资股票：当月在市的 A股、非 ST、上市满 252 个交易日、当天有成交、流通市值不在最小 30%。"""
    codes = p["close"].columns
    mem = members.assign(me=pd.to_datetime(members.month_end).dt.to_period("M"))
    inm = pd.DataFrame(False, index=me, columns=codes)
    for per, g in mem.groupby("me"):
        rows = me[me.to_period("M") == per]
        if len(rows):
            inm.loc[rows, inm.columns.intersection(g.code)] = True
    days = p["close"].index
    ipo = pd.to_datetime(basic.set_index("code").ipoDate.reindex(codes), errors="coerce")
    ipo_pos = pd.Series(days.searchsorted(ipo.fillna(pd.Timestamp("2100-01-01")).to_numpy()), index=codes)
    me_pos = pd.Series(days.searchsorted(me), index=me)
    age = pd.DataFrame(me_pos.to_numpy()[:, None] - ipo_pos.to_numpy()[None, :], index=me, columns=codes)
    traded = (p["tradestatus"].reindex(me) == 1) & (p["volume"].reindex(me) > 0)
    ok = inm & traded & (p["isST"].reindex(me) != 1) & (age >= spec.MIN_AGE) & mcap.reindex(me).notna()
    cap = mcap.reindex(me).where(ok)
    small = cap.rank(axis=1, pct=True) <= spec.SMALL_CUT
    return (ok & ~small).fillna(False)
