"""从现有持仓到目标配置：本月目标权重、整手调仓单、分期执行、税务所需字段。系统只给数字，执行由用户决定。"""
import math

import pandas as pd

from quant.backtest.strategies import rebalance_dates
from quant.research import p3

PENDING = "待补"


def last_complete_month_end(index: pd.DatetimeIndex, today: pd.Timestamp) -> pd.DatetimeIndex:
    """可用作信号的月末调仓日。日期等于或晚于今天的那根 K 线可能还没收盘，不用；
    数据最后一天之后当月还有工作日、且今天仍在当月时，当月不算完整（月末是节假日的月份，过了当月就算完整）。"""
    idx = index[index.normalize() < today.normalize()]
    dates = rebalance_dates(pd.DataFrame(index=idx), "end")
    last = idx[-1]
    month_end = last.to_period("M").end_time.normalize()
    weekdays_left = len(pd.bdate_range(last + pd.Timedelta(days=1), month_end)) > 0
    if weekdays_left and today.to_period("M") == last.to_period("M"):
        dates = dates[dates < last.to_period("M").start_time]
    return dates


def target_weights(px: pd.DataFrame, a: dict, base: dict, signal: str,
                   today: pd.Timestamp | None = None) -> tuple[pd.Timestamp, dict]:
    """用最近一个完整月末的信号算目标权重。"""
    today = pd.Timestamp.today() if today is None else today
    dates = last_complete_month_end(px.index, today)
    w = p3._weights(px, base, signal, a, dates)
    d = w.index[-1]
    return d, {s: float(v) for s, v in w.loc[d].items() if s in base}


def _lots(q: float, lot: int) -> int:
    return int(math.floor(q / lot + 1e-9) * lot)


def transition_orders(holdings: pd.DataFrame, prices: dict[str, float], target: dict[str, float], account: str,
                      lot: dict[str, int], cost_fn) -> pd.DataFrame:
    """先卖后买。目标股数按整手向下取整；买入超出现金时按手减少，保证剩余现金 ≥ 0。"""
    h = holdings[holdings.account == account]
    cash = float(h[h.symbol == "CASH"].shares.sum())
    # 同一标的可能按买入批次分多行，先合并
    held = h[h.symbol != "CASH"].groupby("symbol").shares.sum().astype(float).to_dict()
    nav = cash + sum(q * prices[s] for s, q in held.items())
    want = {s: _lots(w * nav / prices[s], lot[s]) for s, w in target.items() if w > 0}
    rows = []
    for s, q in held.items():
        sell = q - want.get(s, 0)
        if sell > 0:
            v = sell * prices[s]
            c = cost_fn(s, "sell", v)
            cash += v - c
            rows.append({"symbol": s, "side": "卖", "shares": sell, "price": prices[s], "value": v, "cost": c})
    for s in sorted(want, key=lambda k: -target[k]):
        q = want[s] - held.get(s, 0)
        while q > 0:
            v = q * prices[s]
            c = cost_fn(s, "buy", v)
            if v + c <= cash:
                cash -= v + c
                rows.append({"symbol": s, "side": "买", "shares": q, "price": prices[s], "value": v, "cost": c})
                break
            q -= lot[s]
    rows.append({"symbol": "CASH", "side": "剩余", "shares": 0, "price": 1.0, "value": cash, "cost": 0.0})
    return pd.DataFrame(rows)


def tranche_plan(orders: pd.DataFrame, lot: dict[str, int], cost_fn, n: int = 3, cash0: float = 0.0) -> list[pd.DataFrame]:
    """每笔卖单按整手均分到 n 期（余数放最后一期）；每期先卖后买，买单按当期可用现金逐手削减，没买到的顺延到下一期。
    每期末尾一行 CASH 是执行完这一期后账户里的现金。"""
    sells = orders[orders.side == "卖"]
    buys = orders[orders.side == "买"]
    left = {r.symbol: r.shares for r in buys.itertuples()}
    price = {r.symbol: r.price for r in orders.itertuples()}
    parts, cash = [], cash0
    for k in range(n):
        rows = []
        for r in sells.itertuples():
            per = _lots(r.shares / n, lot[r.symbol])
            q = r.shares - per * (n - 1) if k == n - 1 else per
            if q <= 0:
                continue
            v = q * r.price
            c = cost_fn(r.symbol, "sell", v)
            cash += v - c
            rows.append({"symbol": r.symbol, "side": "卖", "shares": q, "price": r.price, "value": v, "cost": c})
        for s in left:
            q = left[s] if k == n - 1 else min(left[s], _lots(left[s] / (n - k), lot[s]) or lot[s])
            while q > 0:
                v = q * price[s]
                c = cost_fn(s, "buy", v)
                if v + c <= cash:
                    cash -= v + c
                    left[s] -= q
                    rows.append({"symbol": s, "side": "买", "shares": q, "price": price[s], "value": v, "cost": c})
                    break
                q -= lot[s]
        rows.append({"symbol": "CASH", "side": "期末现金", "shares": 0, "price": 1.0, "value": cash, "cost": 0.0})
        parts.append(pd.DataFrame(rows))
    return parts


def tax_fields(holdings: pd.DataFrame, prices: dict[str, float], today: pd.Timestamp) -> pd.DataFrame:
    """澳洲资本利得税所需字段（不算税额），每个买入批次一行。50% 折扣要求持有至少 12 个月且买入日、卖出日都不计，
    即卖出日晚于买入日加一年（闰年也按日历年算）。"""
    rows = []
    for r in holdings[holdings.symbol != "CASH"].itertuples():
        cb = r.cost_basis
        bd = pd.to_datetime(r.buy_date) if isinstance(r.buy_date, str) and r.buy_date else None
        days = (today - bd).days if bd is not None else PENDING
        rows.append({"symbol": r.symbol, "shares": r.shares, "price": prices[r.symbol],
                     "cost_basis": PENDING if pd.isna(cb) else cb,
                     "gain": PENDING if pd.isna(cb) else (prices[r.symbol] - cb) * r.shares,
                     "held_days": days, "discount_eligible": PENDING if bd is None else today > bd + pd.DateOffset(years=1)})
    return pd.DataFrame(rows)
