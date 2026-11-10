"""每月调仓单：新投入的钱优先补低配；只有超出目标一定容差或目标为 0 的资产才卖出。系统只给数字，执行由用户决定。"""
from datetime import datetime
from pathlib import Path

import pandas as pd

from quant.portfolio.transition import _lots

BAND = 0.05  # 高出目标超过 5 个百分点才卖（本计划的判断）
OUT_DIR = Path("live/orders")
DISCLAIMER = "> 声明：本调仓单由系统按预设规则生成，不是投资建议；回测不代表未来收益。是否执行、何时执行由你决定。"


def cash_first_orders(holdings: pd.DataFrame, prices: dict[str, float], target: dict[str, float], account: str,
                      lot: dict[str, int], cost_fn, band: float = BAND) -> pd.DataFrame:
    """先卖超配部分（超出目标 > band 卖到目标，目标为 0 全卖），再用现金按缺口买低配资产；整手取整，现金 ≥ 0。"""
    h = holdings[holdings.account == account]
    cash = float(h[h.symbol == "CASH"].shares.sum())
    held = h[h.symbol != "CASH"].groupby("symbol").shares.sum().astype(float).to_dict()
    nav = cash + sum(q * prices[s] for s, q in held.items())
    rows = []
    for s, q in held.items():
        w = target.get(s, 0.0)
        if w <= 0:
            sell = q
        elif q * prices[s] / nav - w > band:
            sell = q - _lots(w * nav / prices[s], lot[s])
        else:
            continue
        if sell > 0:
            v = sell * prices[s]
            c = cost_fn(s, "sell", v)
            cash += v - c
            held[s] = q - sell
            rows.append({"symbol": s, "side": "卖", "shares": sell, "price": prices[s], "value": v, "cost": c})
    gaps = {s: w * nav - held.get(s, 0.0) * prices[s] for s, w in target.items() if w > 0}
    gaps = {s: g for s, g in gaps.items() if g > 0}
    total = sum(gaps.values())
    budget = cash
    for s in sorted(gaps, key=lambda k: -gaps[k]):
        alloc = gaps[s] if total <= budget else budget * gaps[s] / total
        q = _lots(alloc / prices[s], lot[s])
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


def write_orders(month: str, per_account: dict, out_dir: Path = OUT_DIR) -> list[Path]:
    """写 <out_dir>/<YYYY-MM>/调仓单.md 和每个账户一个 CSV；同月重跑覆盖并注明重算时间。"""
    d = Path(out_dir) / month
    rerun = (d / "调仓单.md").exists()
    d.mkdir(parents=True, exist_ok=True)
    now = f"{datetime.now():%Y-%m-%d %H:%M}"
    suffix = f"-重算{datetime.now():%H%M%S}" if rerun else ""  # 首版保留，偏差报告据此判断是否照做
    md = [f"# {month} 调仓单", "", f"{'重算于' if rerun else '生成于'} {now}。新投入的钱优先补低配；"
          f"只有高出目标超过 {BAND * 100:.0f} 个百分点、或目标为 0 的资产才卖出。", ""]
    paths = []
    for label, x in per_account.items():
        o, ccy = x["orders"], x["ccy"]
        md += [f"## {label}（信号日 {x['sig_date']:%Y-%m-%d}，价格日期 {x['price_date']:%Y-%m-%d}）", "",
               "目标：" + "、".join(f"{s} {w * 100:g}%" for s, w in x["target"].items()), ""]
        trades = o[o.symbol != "CASH"]
        if trades.empty:
            md.append("本月无需交易。")
        else:
            md += ["| 方向 | 代码 | 数量 | 参考价 | 金额 | 成本 |", "|---|---|---|---|---|---|"]
            md += [f"| {r.side} | {r.symbol} | {r.shares:.0f} | {r.price:,.2f} | {r.value:,.2f} {ccy} | {r.cost:,.2f} |"
                   for r in trades.itertuples()]
        md += ["", f"执行后剩余现金约 {o[o.symbol == 'CASH'].value.iloc[0]:,.2f} {ccy}。", ""]
        p = d / f"{label}{suffix}.csv"
        o.to_csv(p, index=False)
        paths.append(p)
    md += ["交易完成后请更新 `config/holdings.csv`；入金或出金记到 `config/flows.csv`。", "", DISCLAIMER, ""]
    (d / f"调仓单{suffix}.md").write_text("\n".join(md))
    return [d / f"调仓单{suffix}.md", *paths]


def account_inputs(label: str, h: pd.DataFrame, fx: dict, today: pd.Timestamp) -> dict:
    """一个账户本月的目标权重、最新价格（含价格日期）和整手规则。"""
    from quant.data.update import get_index, get_price, latest_quote
    from quant.portfolio.transition import target_weights
    from quant.research import p3
    from quant.live import plan
    from quant.research.p5 import BROKER, STOCKS

    e, split, signal = plan.core(label)
    a, px = plan.build(label, get_price, get_index, fx)
    base = p3._base_weights(a, e, p3.SPLITS[split])
    sig_date, target = target_weights(px, a, base, signal, today)
    hh = h[h.account == BROKER[label]]
    quotes = {s: latest_quote(s, a["market"], "stock" if s in STOCKS else "etf")
              for s in set(target) | set(hh.symbol[hh.symbol != "CASH"])}
    prices = {s: q[1] for s, q in quotes.items()}
    return {"account": BROKER[label], "ccy": a["ccy"], "sig_date": sig_date, "target": target, "prices": prices,
            "price_date": min(q[0] for q in quotes.values()), "lot": {s: 100 if a["cn"] else 1 for s in prices}}


def main() -> int:
    import warnings
    for cat in (FutureWarning, DeprecationWarning, pd.errors.PerformanceWarning):
        warnings.filterwarnings("ignore", category=cat)
    from quant.data.update import get_price
    from quant.portfolio.holdings import load_holdings
    from quant.live.plan import LABELS
    from quant.research.p5 import cost_fn

    today = pd.Timestamp.today().normalize()
    fx = {"AUDUSD": get_price("AUDUSD", "FX", "fx"), "AUDCNY": get_price("AUDCNY", "FX", "fx")}
    h = load_holdings()
    per = {}
    for label in LABELS:
        x = account_inputs(label, h, fx, today)
        x["orders"] = cash_first_orders(h, x["prices"], x["target"], x["account"], x["lot"], cost_fn(label))
        per[label] = x
    paths = write_orders(f"{today:%Y-%m}", per)
    snap = paths[0].parent / "持仓快照.csv"
    if not snap.exists():  # 只存首次出单时的持仓，偏差报告用来判断是否照单执行
        h.to_csv(snap, index=False)
    for p in paths:
        print("已生成：", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
