"""生成月度目标权重（行=调仓日，列=标的）。某标的还没有价格时权重为 0。"""
import pandas as pd


def month_ends(prices: pd.DataFrame) -> pd.DatetimeIndex:
    idx = prices.index
    return pd.DatetimeIndex(pd.Series(idx, index=idx).groupby(idx.to_period("M")).max().values)


def buy_and_hold(prices: pd.DataFrame, weights: dict[str, float]) -> pd.DataFrame:
    d = month_ends(prices)[0]
    row = {s: (w if pd.notna(prices.at[d, s]) else 0.0) for s, w in weights.items()}
    return pd.DataFrame([row], index=[d]).reindex(columns=prices.columns, fill_value=0.0)


def sma_timing(prices: pd.DataFrame, asset: str, months: int = 10, risk_off: str | None = None) -> pd.DataFrame:
    me = month_ends(prices)
    m = prices.loc[me, asset]
    sma = m.rolling(months, min_periods=months).mean()
    rows = []
    for d in me:
        if pd.isna(sma.at[d]) or pd.isna(m.at[d]):
            continue
        row = {c: 0.0 for c in prices.columns}
        if m.at[d] > sma.at[d]:
            row[asset] = 1.0
        elif risk_off is not None and pd.notna(prices.at[d, risk_off]):
            row[risk_off] = 1.0
        rows.append(pd.Series(row, name=d))
    return pd.DataFrame(rows)


def rebalance_dates(prices: pd.DataFrame, mode: str) -> pd.DatetimeIndex:
    """每月一个调仓日：start=当月首个交易日，mid=15 日或之后首个交易日，end=当月最后一个交易日。"""
    idx = prices.index
    s = pd.Series(idx, index=idx)
    g = s.groupby(idx.to_period("M"))
    if mode == "start":
        return pd.DatetimeIndex(g.min().values)
    if mode == "end":
        return pd.DatetimeIndex(g.max().values)
    mids = s[s.index.day >= 15].groupby(s[s.index.day >= 15].index.to_period("M")).min()
    return pd.DatetimeIndex(mids.values)


def static_mix(prices: pd.DataFrame, weights: dict[str, float], dates: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    for d in dates:
        row = {c: 0.0 for c in prices.columns}
        for s, w in weights.items():
            row[s] = w if pd.notna(prices.at[d, s]) else 0.0
        rows.append(pd.Series(row, name=d))
    return pd.DataFrame(rows)


def _signal(samples: pd.Series, kind: str) -> float | None:
    """samples：截至当前调仓日（含）的采样价格。数据不足返回 None。"""
    s = samples.dropna()
    if kind == "sma10":
        if len(s) < 10:
            return None
        return 1.0 if s.iloc[-1] > s.iloc[-10:].mean() else 0.0
    if len(s) < 13:
        return None
    now = s.iloc[-1]
    return sum(now > s.iloc[-1 - k] for k in (3, 6, 9, 12)) / 4


def trend_mix(prices: pd.DataFrame, weights: dict[str, float], filtered: list[str], safe: str | None,
              signal: str, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """filtered 中的资产按信号保留 w×信号，其余转给 safe（safe 未上市或为 None 时留现金）。"""
    sampled = prices.loc[dates]
    rows = []
    for i, d in enumerate(dates):
        hist = sampled.iloc[: i + 1]
        sig = {}
        for s in filtered:
            if weights.get(s, 0) > 0:
                sig[s] = _signal(hist[s], signal)
        if any(v is None for v in sig.values()):
            continue
        row = {c: 0.0 for c in prices.columns}
        safe_ok = safe is not None and pd.notna(prices.at[d, safe])
        for s, w in weights.items():
            if pd.isna(prices.at[d, s]):
                continue
            keep = w * sig.get(s, 1.0)
            row[s] += keep
            if safe_ok and s != safe:
                row[safe] += w - keep
        rows.append(pd.Series(row, name=d))
    return pd.DataFrame(rows)
