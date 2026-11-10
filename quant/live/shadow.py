"""影子盘：完全按回测假设运行的纸面组合（每月全额再平衡到目标、整手、扣成本），用来和用户实际持仓、模拟盘成交、回测对照。
起始资金 = 开始记录那天的账户市值，第一天直接按目标建仓，不模拟过渡期。"""
import json
from pathlib import Path

import pandas as pd

from quant.portfolio.transition import transition_orders

STATE_DIR = Path("live/shadow")


def init_shadow(account: str, value_local: float, day: pd.Timestamp) -> dict:
    return {"account": account, "start": f"{day:%Y-%m-%d}", "start_value": value_local, "cash": value_local,
            "positions": {}, "last_rebalance_month": None, "history": [], "marks": []}


def rebalance(state: dict, month: str, target: dict, prices: dict, lot: dict, cost_fn, day: pd.Timestamp | None = None,
              price_date: pd.Timestamp | None = None) -> dict:
    """按回测口径全额再平衡到目标；同一月份只调一次。"""
    if state["last_rebalance_month"] == month:
        return state
    rows = [{"account": "shadow", "symbol": s, "shares": q} for s, q in state["positions"].items()]
    rows.append({"account": "shadow", "symbol": "CASH", "shares": state["cash"]})
    o = transition_orders(pd.DataFrame(rows), prices, target, "shadow", lot, cost_fn)
    pos = dict(state["positions"])
    for r in o[o.symbol != "CASH"].itertuples():
        pos[r.symbol] = pos.get(r.symbol, 0) + (r.shares if r.side == "买" else -r.shares)
    pos = {s: int(q) for s, q in pos.items() if q > 0}
    day = pd.Timestamp.today().normalize() if day is None else day
    trades = o[o.symbol != "CASH"].to_dict("records")
    return {**state, "positions": pos, "cash": float(o[o.symbol == "CASH"].value.iloc[0]), "last_rebalance_month": month,
            "history": [*state["history"], {"month": month, "date": f"{day:%Y-%m-%d}",
                                             "price_date": f"{(price_date if price_date is not None else day):%Y-%m-%d}", "target": target,
                                             "orders": [{k: (v if k in ("symbol", "side") else float(v))
                                                         for k, v in t.items()} for t in trades]}]}


def value(state: dict, prices: dict) -> float:
    return state["cash"] + sum(q * prices[s] for s, q in state["positions"].items())


def mark(state: dict, day: pd.Timestamp, prices: dict, price_date: pd.Timestamp | None = None) -> dict:
    """记当天本币市值（及所用价格的日期）；同一天重复标记时替换。"""
    d = f"{day:%Y-%m-%d}"
    pdt = f"{(price_date if price_date is not None else day):%Y-%m-%d}"
    marks = [m for m in state["marks"] if m["date"] != d] + [{"date": d, "price_date": pdt, "value": value(state, prices)}]
    return {**state, "marks": marks}


def save_state(state: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1))


def load_state(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def main() -> int:
    import warnings
    for cat in (FutureWarning, DeprecationWarning, pd.errors.PerformanceWarning):
        warnings.filterwarnings("ignore", category=cat)
    from quant.data.update import get_price, latest_quote
    from quant.live.monthly import account_inputs
    from quant.portfolio.holdings import load_holdings
    from quant.live.plan import LABELS
    from quant.research.p5 import STOCKS, cost_fn

    today = pd.Timestamp.today().normalize()
    fx = {"AUDUSD": get_price("AUDUSD", "FX", "fx"), "AUDCNY": get_price("AUDCNY", "FX", "fx")}
    h = load_holdings()
    for label in LABELS:
        x = account_inputs(label, h, fx, today)
        path = STATE_DIR / f"{label}.json"
        st = load_state(path)
        if st is None:
            hh = h[h.account == x["account"]]
            v = float(sum(r.shares if r.symbol == "CASH" else r.shares * x["prices"][r.symbol] for r in hh.itertuples()))
            st = init_shadow(label, v, today)
        prices = dict(x["prices"])
        for s in st["positions"]:
            if s not in prices:
                prices[s] = latest_quote(s, "CN" if label == "A股账户" else "US", "stock" if s in STOCKS else "etf")[1]
        st = rebalance(st, f"{today:%Y-%m}", x["target"], prices, x["lot"], cost_fn(label), today, x["price_date"])
        st = mark(st, today, prices, x["price_date"])
        save_state(st, path)
        print(f"{label} 影子盘：市值 {st['marks'][-1]['value']:,.2f} {x['ccy']}，持仓 {st['positions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
