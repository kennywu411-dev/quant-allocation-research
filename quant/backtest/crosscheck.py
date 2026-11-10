"""用开源框架 bt 跑同一组权重，交叉核对本引擎（零成本、允许零碎股）。"""
import bt
import pandas as pd


def run_bt(prices: pd.DataFrame, weights: pd.DataFrame) -> pd.Series:
    px = prices.dropna()
    dates = px.index
    # 本引擎在调仓日的下一个交易日成交，这里把权重日期挪到下一个交易日，让 bt 当天收盘成交
    shifted = {}
    for d, row in weights.iterrows():
        nxt = dates[dates > d]
        if len(nxt):
            shifted[nxt[0]] = row
    w = pd.DataFrame(shifted).T.reindex(columns=px.columns).fillna(0.0)
    strat = bt.Strategy("s", [bt.algos.WeighTarget(w), bt.algos.Rebalance()])
    res = bt.run(bt.Backtest(strat, px, integer_positions=False, progress_bar=False))
    nav = res.prices["s"]
    nav.index = pd.DatetimeIndex(nav.index)
    return nav.loc[dates[0]:]
