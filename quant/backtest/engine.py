"""月度调仓回测引擎：信号在调仓日收盘产生，下一个交易日按收盘价成交；先卖后买，现金不为负。"""
import math
from dataclasses import dataclass

import pandas as pd

from quant.backtest.costs import CostModel


@dataclass
class BacktestResult:
    nav: pd.Series
    positions: pd.DataFrame
    cash: pd.Series
    trades: pd.DataFrame
    total_cost: float
    turnover: float  # 单边年化换手：成交额 / 2 / 平均净值 / 年数
    blocked: int = 0  # 被涨跌停、停牌、缺价挡住的订单次数


def limit_pct(symbol: str) -> float:
    return 0.20 if symbol.startswith(("300", "301", "688")) else 0.10


def _round(q: float, lot: int, fractional: bool) -> float:
    return q if fractional else math.floor(q / lot) * lot


MIN_FRACTIONAL_TRADE = 1.0  # 碎股模式下低于 1 个货币单位的调整不下单（真实投资者不会为几分钱付最低佣金）


def _affordable(cash: float, px: float, m: CostModel) -> float:
    """现金最多能买多少股（含成本），按佣金是否触及最低佣金分两种情况求解。"""
    avail = cash - m.per_order
    if avail <= 0:
        return 0.0
    qa = avail / (px * (1 + m.slippage + m.commission_rate))
    if qa * px * m.commission_rate >= m.min_commission:
        return qa
    return max((avail - m.min_commission) / (px * (1 + m.slippage)), 0.0)


def run_backtest(
    prices: pd.DataFrame,
    weights: pd.DataFrame,
    costs: dict[str, CostModel],
    initial: float = 100_000.0,
    cn_rules: bool = False,
    tradable: pd.DataFrame | None = None,
    fractional: bool = False,
) -> BacktestResult:
    raw = prices.sort_index()
    val_px = raw.ffill()
    dates = raw.index
    syms = list(raw.columns)
    daily_ret = raw / raw.ffill().shift(1) - 1  # 用上一个有效收盘价，停牌复牌日也能判断涨跌停

    exec_map: dict[pd.Timestamp, pd.Series] = {}
    for d, row in weights.sort_index().iterrows():
        nxt = dates[dates > d]
        if len(nxt):
            exec_map[nxt[0]] = row.reindex(syms).fillna(0.0)

    cash = float(initial)
    pos = {s: 0.0 for s in syms}
    target = None
    trades, navs, cash_hist, pos_hist = [], [], [], []
    traded_value = 0.0
    n_blocked = 0

    def can_trade(t, s, side):
        p = raw.at[t, s]
        if pd.isna(p) or p <= 0:
            return False
        if tradable is not None and s in tradable and not bool(tradable.at[t, s]):
            return False
        if cn_rules:
            r = daily_ret.at[t, s]
            lim = limit_pct(s)
            if pd.notna(r) and side == "buy" and r >= lim - 0.002:
                return False
            if pd.notna(r) and side == "sell" and r <= -lim + 0.002:
                return False
        return True

    for t in dates:
        if t in exec_map:
            target = exec_map[t]
        bought_today = {s: 0.0 for s in syms}
        if target is not None:
            nav_now = cash + sum(pos[s] * val_px.at[t, s] for s in syms if pos[s])
            blocked = False
            want = {}
            for s in syms:
                p = raw.at[t, s]
                if pd.isna(p) or p <= 0:
                    want[s] = pos[s]  # 当天没有价格：不动，若需要调整就顺延
                    if target[s] > 0 or pos[s] > 0:
                        blocked = True
                        n_blocked += 1
                    continue
                want[s] = _round(target[s] * nav_now / p, costs[s].lot, fractional)
            for s in syms:  # 先卖
                q = pos[s] - want[s]
                if q > 1e-12:
                    if not can_trade(t, s, "sell"):
                        blocked = True
                        n_blocked += 1
                        continue
                    q = min(q, pos[s] - bought_today[s]) if cn_rules else q
                    px = raw.at[t, s]
                    c = costs[s].cost("sell", q * px)
                    if fractional and (q * px < MIN_FRACTIONAL_TRADE or q * px <= c):
                        continue
                    cash += q * px - c
                    pos[s] -= q
                    traded_value += q * px
                    trades.append((t, s, "sell", q, px, c))
            for s in syms:  # 后买
                q = want[s] - pos[s]
                if q > 1e-12:
                    if not can_trade(t, s, "buy"):
                        blocked = True
                        n_blocked += 1
                        continue
                    px, m = raw.at[t, s], costs[s]
                    q = min(q, _affordable(cash, px, m))
                    q = q * (1 - 1e-12) if fractional else _round(q, m.lot, False)
                    while q > 0 and q * px + m.cost("buy", q * px) > cash + 1e-9:
                        q = q * (1 - 1e-9) if fractional else q - m.lot
                    if q <= 0 or (fractional and q * px < MIN_FRACTIONAL_TRADE):
                        continue
                    c = m.cost("buy", q * px)
                    cash -= q * px + c
                    pos[s] += q
                    bought_today[s] += q
                    traded_value += q * px
                    trades.append((t, s, "buy", q, px, c))
            target = target if blocked else None
        assert cash >= -1e-6, f"{t:%Y-%m-%d} 现金为负：{cash}"
        navs.append(cash + sum(pos[s] * val_px.at[t, s] for s in syms if pos[s]))
        cash_hist.append(cash)
        pos_hist.append(dict(pos))

    nav = pd.Series(navs, index=dates, name="nav")
    tr = pd.DataFrame(trades, columns=["date", "symbol", "side", "shares", "price", "cost"])
    years = max((dates[-1] - dates[0]).days / 365.25, 1e-9)
    return BacktestResult(
        nav=nav,
        positions=pd.DataFrame(pos_hist, index=dates),
        cash=pd.Series(cash_hist, index=dates, name="cash"),
        trades=tr,
        total_cost=float(tr["cost"].sum()) if len(tr) else 0.0,
        turnover=traded_value / 2 / float(nav.mean()) / years,
        blocked=n_blocked,
    )
