"""每月偏差报告：影子盘 vs 回测的偏差拆解、模拟盘成交价差与未成交、用户是否照调仓单执行（单列，不混进成交偏差）。"""
import argparse
from pathlib import Path

import pandas as pd

from quant.live.shadow import STATE_DIR, load_state

MIN_MONTHS = 3
DISCLAIMER = "> 声明：本报告只解释系统数字的来源，不是投资建议；回测和模拟成交都不代表未来收益。"


def decompose(shadow_ret: float, backtest_ret: float, ideal_ret: float, shadow_cost: float) -> dict:
    """影子盘 − 回测 = 整手/现金/分红及其他（兜底项）+ 影子盘成本 + 回测自身的成本与口径（理想无摩擦收益 − 回测收益）。各项之和恒等于合计。"""
    gross = shadow_ret + shadow_cost
    return {"整手、现金、分红及其他": gross - ideal_ret, "影子盘成本": -shadow_cost,
            "回测自身成本与口径": ideal_ret - backtest_ret, "合计": shadow_ret - backtest_ret}


def slippage(log: pd.DataFrame, fills: pd.DataFrame) -> pd.DataFrame:
    """模拟盘每笔订单：成交价差金额（负数 = 对我们不利）和未成交金额（按参考价）。"""
    m = log.merge(fills[["order_id", "status", "qty", "dealt_qty", "dealt_avg_price"]], on="order_id", how="left")
    m["dealt_qty"] = m.dealt_qty.fillna(0).astype(float)
    m["status"] = m.status.fillna("未查到")
    sign = m.side.map({"买": -1, "卖": 1})
    m["slip_value"] = sign * (m.dealt_avg_price.fillna(m.ref_price) - m.ref_price) * m.dealt_qty
    m["unfilled_value"] = (m.shares - m.dealt_qty) * m.ref_price
    return m[["order_id", "symbol", "side", "shares", "dealt_qty", "status", "slip_value", "unfilled_value"]]


def followed(before: pd.DataFrame, after: pd.DataFrame, orders: pd.DataFrame, account: str) -> pd.DataFrame:
    """调仓单计划的股数变化 vs 用户实际持仓变化。"""
    q = lambda h: h[(h.account == account) & (h.symbol != "CASH")].groupby("symbol").shares.sum()  # noqa: E731
    b, a = q(before), q(after)
    rows = []
    for r in orders[orders.symbol != "CASH"].itertuples():
        plan = r.shares if r.side == "买" else -r.shares
        act = float(a.get(r.symbol, 0) - b.get(r.symbol, 0))
        if act == plan:
            st = "已执行"
        elif act == 0:
            st = "没照做"
        elif act * plan > 0 and abs(act) < abs(plan):
            st = "部分执行"
        else:
            st = "与计划不符"
        rows.append({"symbol": r.symbol, "计划": plan, "实际": act, "状态": st})
    return pd.DataFrame(rows, columns=["symbol", "计划", "实际", "状态"])


def _pp(x: float) -> str:
    return f"{x * 100:+.2f} 个百分点"


def render(ctx: dict) -> str:
    out = [f"# P6 偏差报告 {ctx['month']}", ""]
    if ctx["months_recorded"] < MIN_MONTHS:
        out += [f"**记录未满 3 个月**（已有 {ctx['months_recorded']} 个月），还不能对“偏差可以解释”下结论。", ""]
    for label, x in ctx["accounts"].items():
        out += [f"## {label}（{x['window']}）", "", "### 偏差拆解：影子盘 vs 回测", "",
                "影子盘按回测假设成交（整手、扣成本），回测是同一规则的历史模拟。差额拆成：", "",
                "| 项目 | 贡献 |", "|---|---|"]
        out += [f"| {k} | {_pp(v)} |" for k, v in x["decomp"].items()]
        out += ["", "“整手、现金、分红及其他”：影子盘买不满一手的零头留作现金，且影子盘用不复权价标记（分红不计入），回测用复权价。", ""]
        out += ["### 模拟盘成交", ""]
        s = x.get("slip")
        if s is None:
            out += [x.get("paper_note", "本账户没有模拟盘记录。"), ""]
        elif s.empty:
            out += ["本月没有模拟盘订单。", ""]
        else:
            out += ["| 代码 | 方向 | 计划 | 成交 | 状态 | 成交价差 | 未成交金额 |", "|---|---|---|---|---|---|---|"]
            out += [f"| {r.symbol} | {r.side} | {r.shares:.0f} | {r.dealt_qty:.0f} | {r.status} | {r.slip_value:,.2f} | "
                    f"{r.unfilled_value:,.2f} |" for r in s.itertuples()]
            out += ["", f"合计成交价差 {s.slip_value.sum():,.2f} {x['ccy']}（负数为不利），未成交 {s.unfilled_value.sum():,.2f} {x['ccy']}。", ""]
        out += ["### 你是否照调仓单执行（没照做的部分不计入成交偏差）", ""]
        f = x["followed"]
        if f is None or f.empty:
            out += ["没有本月调仓单或持仓快照。", ""]
        else:
            out += ["| 代码 | 计划 | 实际 | 状态 |", "|---|---|---|---|"]
            out += [f"| {r.symbol} | {r.计划:+.0f} | {r.实际:+.0f} | {r.状态} |" for r in f.itertuples()]
            out.append("")
    out += [DISCLAIMER, ""]
    return "\n".join(out)


def prev_month(today: pd.Timestamp) -> str:
    """上一个自然月（偏差报告默认统计上月）。"""
    return str(today.to_period("M") - 1)


def _window(st: dict, month: str):
    """本月调仓日（起点）和下一次调仓日或最后一个标记日（终点）。"""
    hist = [h for h in st["history"] if h["month"] == month]
    if not hist:
        return None
    h = hist[0]
    later = sorted((x for x in st["history"] if x["month"] > month), key=lambda x: x["date"])
    marks = {m["date"]: m for m in st["marks"]}
    cost = lambda x: sum(o["cost"] for o in x["orders"])  # noqa: E731
    pdate = lambda m: pd.Timestamp(m.get("price_date", m["date"]))  # noqa: E731
    v0 = marks[h["date"]]["value"] + cost(h)
    if later:  # 终点标记已扣下次调仓成本，加回
        end = later[0]
        v1 = marks[end["date"]]["value"] + cost(end)
    else:
        end = marks[max(marks)]
        v1 = end["value"]
    return h, pdate(h), pdate(end), v0, v1


def main() -> int:
    import warnings
    for cat in (FutureWarning, DeprecationWarning, pd.errors.PerformanceWarning):
        warnings.filterwarnings("ignore", category=cat)
    from quant.backtest.strategies import rebalance_dates
    from quant.data.update import get_index, get_price
    from quant.live.moomoo_paper import PaperBroker
    from quant.portfolio.holdings import load_holdings
    from quant.research import p3
    from quant.live import plan
    from quant.research.p5 import BROKER

    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=prev_month(pd.Timestamp.today()))
    month = ap.parse_args().month
    fx = {"AUDUSD": get_price("AUDUSD", "FX", "fx"), "AUDCNY": get_price("AUDCNY", "FX", "fx")}
    h_now = load_holdings()
    odir = Path("live/orders") / month
    accounts, months = {}, 0
    for label in plan.LABELS:
        e, split, signal = plan.core(label)
        st = load_state(STATE_DIR / f"{label}.json")
        w = _window(st, month) if st else None
        if w is None:
            print(f"{label}：影子盘没有 {month} 的调仓记录，跳过")
            continue
        months = max(months, len({x["month"] for x in st["history"]}))
        hist, d0, d1, v0, v1 = w
        a, px = plan.build(label, get_price, get_index, fx)
        base = p3._base_weights(a, e, p3.SPLITS[split])
        local = p3.run_trial(px, base, signal, a, fx, rebalance_dates(px, "end")[12])[2]
        at = lambda s, d: float(s.asof(d))  # noqa: E731
        ideal = sum(wt * (at(px[s], d1) / at(px[s], d0) - 1) for s, wt in hist["target"].items() if wt > 0)
        costs = sum(o["cost"] for o in hist["orders"])
        x = {"window": f"{d0:%Y-%m-%d} 至 {d1:%Y-%m-%d}", "ccy": a["ccy"],
             "decomp": decompose(v1 / v0 - 1, at(local, d1) / at(local, d0) - 1, ideal, costs / v0), "slip": None}
        snap, ofile = odir / "持仓快照.csv", odir / f"{label}.csv"
        x["followed"] = (followed(pd.read_csv(snap, dtype={"symbol": str}), h_now, pd.read_csv(ofile, dtype={"symbol": str}),
                                  BROKER[label]) if snap.exists() and ofile.exists() else None)
        plog = Path("live/paper") / f"{month}.csv"
        if label == "美股账户" and plog.exists():
            b = None
            try:
                b = PaperBroker()
                fills = b.history_orders(f"{month}-01", f"{max(d1, pd.Timestamp.today()):%Y-%m-%d}")
                x["slip"] = slippage(pd.read_csv(plog, dtype={"order_id": str}), fills)
            except Exception as err:  # OpenD 没开时如实写明
                x["paper_note"] = f"模拟盘成交没取到：{err}"
            finally:
                if b is not None:
                    b.close()
        elif label == "美股账户":
            x["paper_note"] = "本月没有下到模拟盘的订单（OpenD 未登录或未运行 --sync）。"
        accounts[label] = x
    path = Path("reports") / f"P6-偏差-{month}.md"
    path.write_text(render({"month": month, "months_recorded": months, "accounts": accounts}))
    print("已生成：", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
