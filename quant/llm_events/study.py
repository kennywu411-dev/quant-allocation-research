"""事件研究与月度情绪因子。判定标准在运行前写进本文件（2026-11-11），提交记录可查。

一、时点（防前视）
- 巨潮公告日期只到日，不知道是盘前、盘中还是收盘后发布。保守处理：事件日 t0 = 公告日当天或之后的第一个交易日，
  主口径从 t0 收盘开始算，**不含 t0 当天的反应**；含 t0 当天（从 t0-1 收盘算）的数字只作参考，不参与判定。
- 超额收益 = 个股后复权日收益 - 沪深300 日收益。

二、事件研究（日历时间组合，处理窗口重叠）
- 每个交易日 τ，取所有 t0 < τ ≤ t0+k 的事件（持有期第 1 到 k 天），按组求当日平均超额收益，得到每日序列；
  多空序列 = 实质性利好组 − 实质性利空组（两组当天都有事件的日子）。
- 均值 × k ≈ 持有 k 天的累计超额；t 值用 Newey-West（滞后 k 天）。
- 主假设（只有一个，门槛 t ≥ 2）：Haiku 4.5 在其知识截止之后的干净样本（2025-08-01 起）上，k = 5 的多空序列均值 > 0。
- 次要检验（很多个，门槛 t ≥ 3）：其他模型、其他样本段、k = 1 / 20、按事件类型的单边检验；词典基线同口径对照。

三、大模型自身的前视偏差
- 每个模型按训练数据截止日分为“截止前”（模型可能见过后来的结果）和“截止后”（干净）两段分别报告。
- 2025-08 至 2026-06：Haiku 5.5 已见过、Haiku 4.5 没见过；同一批公告上两个模型多空序列之差（同日配对）就是前视带来的增益估计。

四、月度情绪因子
- 月末 t 的因子 = 当月（上月最后一个交易日之后、本月最后一个交易日之前，不含最后一天）实质性公告的 方向 × 强度 之和；
  没有公告记 0。最后一个交易日的公告可能在收盘后发布，留到下个月用。
- 沿用 quant/factors 的单因子检验（当前沪深300 成分股、剔除次新股和月末停牌、RankIC、五分组、换手成本）。
- 判定：全期 RankIC t ≥ 3，且模型截止日之后的干净段 RankIC 均值同号，才算显著（evaluate.verdict 的口径）。"""
import numpy as np
import pandas as pd

K = (1, 5, 20)
K_MAIN = 5
T_MAIN, T_SECONDARY = 2.0, 3.0
MAIN_MODEL, MAIN_START = "claude-haiku-4-5", "2025-08-01"
OVERLAP = ("2025-08-01", "2026-06-30")  # Haiku 5.5 见过、Haiku 4.5 没见过
DIR_SIGN = {"利好": 1, "中性": 0, "利空": -1}


def nw_t(x: pd.Series, lags: int) -> float:
    """Newey-West 调整的均值 t 值。"""
    x = x.dropna().to_numpy(float)
    n = len(x)
    if n < 3:
        return float("nan")
    e = x - x.mean()
    s = e @ e / n
    for l in range(1, min(lags, n - 1) + 1):
        s += 2 * (1 - l / (lags + 1)) * (e[l:] @ e[:-l]) / n
    return float(x.mean() / np.sqrt(s / n)) if s > 0 else float("nan")


def event_dates(dates: pd.Series, calendar: pd.DatetimeIndex) -> pd.Series:
    """公告日 → t0（当天或之后第一个交易日）；超出日历的为 NaT。"""
    pos = calendar.searchsorted(pd.to_datetime(dates).to_numpy())
    out = pd.Series(pd.NaT, index=dates.index, dtype="datetime64[ns]")
    ok = pos < len(calendar)
    out[ok] = calendar[pos[ok]]
    return out


def abnormal(close: pd.DataFrame, index: pd.Series) -> pd.DataFrame:
    """每日超额收益（个股 - 指数）；个股停牌日没有收益（NaN）。"""
    idx = close.index
    r = close.pct_change(fill_method=None)
    m = index.reindex(idx).pct_change(fill_method=None)
    return r.sub(m, axis=0)


def calendar_series(ev: pd.DataFrame, ar: pd.DataFrame, k: int, include_t0: bool = False) -> pd.DataFrame:
    """ev: code, t0, group。返回每个交易日各组正处在持有期内事件的平均超额收益（列 = 组）。"""
    days = ar.index
    pos = {d: i for i, d in enumerate(days)}
    acc: dict[tuple, list] = {}
    for code, t0, g in zip(ev.code, ev.t0, ev.group):
        if code not in ar.columns or t0 not in pos:
            continue
        i = pos[t0]
        lo, hi = (i, i + k - 1) if include_t0 else (i + 1, i + k)
        col = ar[code].to_numpy()
        for j in range(lo, min(hi, len(days) - 1) + 1):
            v = col[j]
            if not np.isnan(v):
                acc.setdefault((days[j], g), []).append(v)
    if not acc:
        return pd.DataFrame()
    s = pd.Series({key: float(np.mean(v)) for key, v in acc.items()})
    s.index = pd.MultiIndex.from_tuples(s.index)
    return s.unstack()


def spread_stats(cs: pd.DataFrame, k: int, pos: str = "利好", neg: str = "利空") -> dict:
    """多空序列：均值×k 当作 k 日累计超额，NW 滞后 k 的 t 值。"""
    if cs.empty or pos not in cs or neg not in cs:
        return {"n_days": 0, "car": float("nan"), "t": float("nan")}
    ls = (cs[pos] - cs[neg]).dropna()
    return {"n_days": int(len(ls)), "car": float(ls.mean() * k), "t": nw_t(ls, k),
            "car_pos": float(cs[pos].dropna().mean() * k), "car_neg": float(cs[neg].dropna().mean() * k)}


def events(ann: pd.DataFrame, labels: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """公告 + 标注 → 事件表；group = 实质性利好 / 实质性利空 / 其他。"""
    e = ann.merge(labels, on="id", how="inner")
    e["t0"] = event_dates(e.date, calendar)
    e = e.dropna(subset=["t0"])
    e["group"] = np.where(e.material & (e.direction == "利好"), "利好",
                          np.where(e.material & (e.direction == "利空"), "利空", "其他"))
    return e


def monthly_factor(e: pd.DataFrame, calendar: pd.DatetimeIndex, month_ends: pd.DatetimeIndex) -> pd.DataFrame:
    """月末 × 股票 的情绪因子：当月实质性公告 方向×强度 之和（不含当月最后一个交易日的公告）；没有公告记 0。"""
    last_td = pd.Series(calendar, index=calendar).groupby(calendar.to_period("M")).max()
    x = e[e.material].copy()
    x["v"] = x.direction.map(DIR_SIGN) * x.strength
    per = x.date.dt.to_period("M")
    late = x.date.dt.normalize().to_numpy() >= per.map(last_td).to_numpy()  # 最后一个交易日及之后的，顺延到下月
    x["me"] = (per + late.astype(int)).dt.to_timestamp(how="end").dt.normalize()
    f = x.groupby(["me", "code"]).v.sum().unstack()
    return f.reindex(month_ends).fillna(0.0)
