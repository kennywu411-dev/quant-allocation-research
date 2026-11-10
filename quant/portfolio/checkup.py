"""持仓体检：按当前股数回放组合历史净值（澳元），以及相关性、风险贡献、压力区间。"""
import numpy as np
import pandas as pd

from quant.fx import to_aud
from quant.metrics import drawdown

STRESS_WINDOWS = {
    "2008 金融危机": ("2008-09-01", "2009-03-31"),
    "2015 A股股灾": ("2015-06-01", "2016-02-29"),
    "2018 贸易战熊市": ("2018-01-01", "2018-12-31"),
    "2020 新冠暴跌": ("2020-02-15", "2020-03-31"),
    "2022 加息熊市": ("2022-01-01", "2022-12-31"),
    "2024 初微盘崩盘": ("2024-01-01", "2024-02-29"),
}


def current_values_aud(h: pd.DataFrame, last_prices: dict[str, float], fx_last: dict[str, float]) -> pd.Series:
    """各持仓按最新实际（不复权）价格换算的澳元市值。fx_last: {'USD': AUDUSD, 'CNY': AUDCNY, 'AUD': 1}。"""
    vals = {}
    for r in h.itertuples():
        local = r.shares if r.symbol == "CASH" else r.shares * last_prices[r.symbol]
        key = r.symbol if r.symbol != "CASH" else f"CASH_{r.ccy}"
        vals[key] = vals.get(key, 0.0) + local / fx_last[r.ccy]
    return pd.Series(vals)


def fill_with_proxy(series: pd.Series, proxy: pd.Series, vol_scale: bool = False) -> tuple[pd.Series, pd.Timestamp | None]:
    series = series.dropna()
    first = series.index[0]
    before = proxy.loc[:first].dropna()
    if len(before) <= 1:
        return series, None
    r = before.pct_change().fillna(0.0)
    if vol_scale:
        real_vol = series.pct_change().std()
        proxy_vol = proxy.loc[first:].pct_change().std()
        if proxy_vol > 0 and pd.notna(real_vol):
            r = r * real_vol / proxy_vol
    # 用（缩放后的）代理收益从真实首日价格往前倒推，真实段保持不变
    path = (1 + r).cumprod()
    back = series.iloc[0] * path / path.iloc[-1]
    filled = pd.concat([back.iloc[:-1], series])
    filled.name = series.name
    return filled, first


def cash_price_aud(ccy: str, fx: dict[str, pd.Series], index: pd.DatetimeIndex) -> pd.Series:
    """1 单位外币现金的澳元价格，让现金带上汇率风险。"""
    return to_aud(pd.Series(1.0, index=index), ccy, fx)


def weighted_nav(weights: pd.Series, prices: pd.DataFrame) -> pd.Series:
    """按今天的权重每日再平衡回放，回答“现在这个组合放回历史会怎样”。"""
    rets = prices[weights.index].pct_change().fillna(0.0)
    nav = (1 + rets @ weights).cumprod() * 100
    nav.name = "nav"
    return nav


def weekly_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """周收益（周五），避免 A股、美股收盘时间不同步低估相关性。"""
    return prices.resample("W-FRI").last().pct_change().dropna(how="all")


def portfolio_nav(h: pd.DataFrame, prices_aud: pd.DataFrame) -> pd.Series:
    """h 中现金行须已换算为澳元金额（ccy=AUD）。返回澳元计价的组合市值序列。"""
    stocks = h[h.symbol != "CASH"]
    cash = float(h.loc[h.symbol == "CASH", "shares"].sum())
    if stocks.empty:
        return pd.Series(cash, index=prices_aud.index, name="nav")
    px = prices_aud[stocks.symbol.tolist()].dropna()
    nav = (px * stocks.set_index("symbol")["shares"]).sum(axis=1) + cash
    nav.name = "nav"
    return nav


def risk_contribution(weights: pd.Series, returns: pd.DataFrame) -> pd.Series:
    w = weights.reindex(returns.columns).fillna(0.0)
    cov = returns.cov().values
    marginal = cov @ w.values
    total = float(w.values @ marginal)
    return pd.Series(w.values * marginal / total, index=returns.columns)


def stress_table(nav: pd.Series) -> pd.DataFrame:
    rows = {}
    for name, (a, b) in STRESS_WINDOWS.items():
        seg = nav.loc[a:b]
        if nav.index[0] > pd.Timestamp(a) or len(seg) < 2:
            rows[name] = {"区间": f"{a} ~ {b}", "收益": np.nan, "最大回撤": np.nan}
        else:
            rows[name] = {"区间": f"{a} ~ {b}", "收益": seg.iloc[-1] / seg.iloc[0] - 1,
                          "最大回撤": float(drawdown(seg).min())}
    return pd.DataFrame(rows).T.astype({"收益": float, "最大回撤": float})
