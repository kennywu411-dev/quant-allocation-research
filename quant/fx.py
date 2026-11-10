"""把各币种价格换算成澳元，并把不同交易日历的序列对齐。只向前填充，不使用未来数据。"""
from typing import Literal

import pandas as pd

_PAIR = {"USD": "AUDUSD", "CNY": "AUDCNY"}


def to_aud(prices: pd.Series, ccy: Literal["USD", "CNY", "AUD"], fx: dict[str, pd.Series]) -> pd.Series:
    if ccy == "AUD":
        return prices.copy()
    rate = fx[_PAIR[ccy]].sort_index()
    idx = rate.index.union(prices.index)
    rate_on_price_dates = rate.reindex(idx).ffill().reindex(prices.index)
    out = (prices / rate_on_price_dates).dropna()
    out.name = prices.name
    return out


def align(series: dict[str, pd.Series]) -> pd.DataFrame:
    return pd.DataFrame(series).sort_index().ffill()


def to_base(prices: pd.Series, ccy: Literal["USD", "CNY", "AUD"], fx: dict[str, pd.Series],
            base: Literal["AUD", "CNY"] = "AUD") -> pd.Series:
    """换算成基准货币。人民币基准经澳元中转：先换成澳元，再乘当日或之前最近一天的 AUDCNY。"""
    if ccy == base:
        return prices.copy()
    aud = to_aud(prices, ccy, fx)
    if base == "AUD":
        return aud
    rate = fx["AUDCNY"].sort_index()
    out = (aud * rate.reindex(rate.index.union(aud.index)).ffill().reindex(aud.index)).dropna()
    out.name = prices.name
    return out
