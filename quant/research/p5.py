"""P5 最终方案：python -m quant.research.p5

目标配置 = P3 核心（P4 无卫星通过）；风控规则用平稳分块自助法比较；过渡调仓单按整手计算。
"""
from datetime import date
from pathlib import Path

import pandas as pd

from quant.backtest import costs
from quant.backtest.strategies import rebalance_dates
from quant.metrics import cagr, max_drawdown
from quant.portfolio.transition import target_weights, tax_fields, tranche_plan, transition_orders
from quant.research import p3
from quant.research.gates import MDD_LIMIT, period_returns
from quant.research.p4 import CORE, SPLIT, substitute
from quant.research.registry import log_trial, new_run_id
from quant.research.riskrule import RULES, evaluate_rules, overlay, pick_rule

BOOT = {"n_paths": 2000, "length": 2520, "mean_block": 63, "seed": 20261031}
BROKER = {"美股账户": "moomoo", "A股账户": "银河"}
NAMES = {"SPY": "标普500 ETF", "IEF": "7-10 年美债 ETF", "TLT": "20 年以上美债 ETF", "GLD": "黄金 ETF",
         "510300": "沪深300 ETF", "510880": "红利 ETF", "511010": "国债 ETF", "518880": "黄金 ETF", "CASH": "现金"}


def _universe(path: Path = Path("config/universe.csv")) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str) if path.exists() else pd.DataFrame(columns=["symbol", "kind", "name"])


_U = _universe()
STOCKS = set(_U.loc[_U.kind == "stock", "symbol"])  # 个股（成本按个股算）；从 config/universe.csv 读，不写死持仓
NAMES = {**dict(zip(_U.loc[_U.kind == "stock", "symbol"], _U.loc[_U.kind == "stock", "name"])), **NAMES}
DECISION = {"date": "2026-10-31", "rule": "无规则",
            "text": "合并回撤到 -15% 时只提醒不交易：停下来复盘，不自动降仓。"}
RULE_TEXT = {"无规则": "不设规则", "减半-回升": "股票部分一半转入国债 ETF，合并回撤回到 -10% 以内时恢复",
             "减半-3月": "股票部分一半转入国债 ETF，满 3 个月（63 个交易日）恢复", "清零-回升": "股票部分全部转入国债 ETF，合并回撤回到 -10% 以内时恢复",
             "清零-3月": "股票部分全部转入国债 ETF，满 3 个月恢复"}


def defensive_weights(base: dict, a: dict) -> dict:
    """防守版：股票部分全部转入账户的国债 ETF（a['safe']），债券和黄金不动。"""
    return substitute(base, a["eq"], [a["safe"]], 1.0)


def cost_fn(label: str):
    def f(s, side, v):
        if label == "美股账户":
            return (costs.us_stock() if s in STOCKS else costs.us_etf()).cost(side, v)
        return (costs.cn_stock() if s in STOCKS else costs.cn_etf()).cost(side, v)
    return f


def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _orders_md(o: pd.DataFrame, ccy: str) -> list[str]:
    out = ["| 资产 | 方向 | 数量 | 价格 | 金额 | 成本 |", "|---|---|---:|---:|---:|---:|"]
    for r in o.itertuples():
        name = f"{r.symbol} {NAMES.get(r.symbol, '')}".strip()
        if r.symbol == "CASH":
            out.append(f"| {name} | {r.side} | | | {r.value:,.2f} {ccy} | |")
        else:
            out.append(f"| {name} | {r.side} | {int(r.shares)} | {r.price:,.2f} | {r.value:,.2f} | {r.cost:,.2f} |")
    return out


def render_rules(rules: pd.DataFrame, pick: str, decision: dict | None = None) -> str:
    """选中规则说明；用户已拍板时写明决定，否则在有更低跌破概率的规则时请用户决定。"""
    best = rules.p_breach20.idxmin()
    out = [f"选法（运行前固定）：跌破 -20% 概率最低；相差不到 1 个百分点时选中位年化更高的。选中：**{pick}**。"]
    rb, rp = rules.loc[best], rules.loc[pick]
    gap = (f"跌破 -20% 概率最低的是“{best}”（{rb.p_breach20 * 100:.2f}%，对比“{pick}” {rp.p_breach20 * 100:.2f}%），"
           f"中位年化只差 {(rp.median_cagr - rb.median_cagr) * 100:.3f} 个百分点")
    if decision and decision["rule"] == pick:
        out += ["", f"**你的决定（{decision['date']}）**：{decision['text']}"
                + (f"备选“{best}”未采用：{gap}，差距在随机误差之内。" if best != pick else "")]
    elif best != pick:
        out += ["", f"**需要你决定**：{gap}。差距在选法的 1 个百分点容差以内，所以按规则选了“{pick}”；"
                f"如果你更看重少跌破 -20%，可以改用“{best}”。注意这点差距在随机误差之内：换随机种子重跑，排序可能反过来。"]
    return "\n".join(out)


def render(ctx: dict) -> str:
    rules, pick, perf = ctx["rules"], ctx["pick"], ctx["perf"]
    out = [f"# P5 最终方案（{ctx['as_of']:%Y-%m-%d}）", "", p3.DISCLAIMER, "",
           "## 一句话结论", "",
           f"两个账户各自持有一组 ETF（股票、债券、黄金），每月末按 10 个月均线决定股票和黄金是否转入国债；"
           f"回测（{perf['window']}，人民币）合并年化 {_pct(perf['full'])}、最差回撤 {_pct(perf['mdd'])}。"
           + (f"实盘合并回撤到 -15% 时执行预设规则：**{RULE_TEXT[pick]}**。" if pick != "无规则" else
            "按运行前定好的选法，-15% 时**不做机械降仓**（各规则降低跌破 -20% 概率的幅度都不到 1 个百分点，见“风控规则”一节）；"
            "-15% 改为复盘提醒。是否改用最接近的备选规则由你决定。") + "P4 的卫星策略都没有通过，不加入。", "",
           "## 目标配置", "",
           f"两个账户按当前市值，美股账户占 {_pct(ctx['w_us'])}，A股账户占 {_pct(1 - ctx['w_us'])}；账户之间不调钱，各自在账户内再平衡。", ""]
    for label, d in ctx["accounts"].items():
        out += [f"### {label}（信号日 {d['sig_date']:%Y-%m-%d}）", "", "| 资产 | 基础权重 | 本月目标权重 |", "|---|---:|---:|"]
        for s, w in d["base"].items():
            out.append(f"| {s} {NAMES.get(s, '')} | {_pct(w)} | {_pct(d['target'].get(s, 0.0))} |")
        out += ["", "基础权重与本月目标不同的地方，是因为该资产在 10 个月均线之下，权重转给了国债。"]
        if d.get("last_data") is not None and d["last_data"] != d["sig_date"]:
            out.append(f"数据最后一天是 {d['last_data']:%Y-%m-%d}，当月最后一个交易日的收盘数据还没出来，所以用上个月末的信号；"
                       "数据更新后重跑本报告，目标权重可能变化。")
        out.append("")
    out += ["## 回测表现（两个账户合并，人民币）", "", "| 指标 | 数值 |", "|---|---:|",
            f"| 样本内年化（至 2019 年） | {_pct(perf['is'])} |", f"| 样本外年化（2020 年起） | {_pct(perf['oos'])} |",
            f"| 全期年化 | {_pct(perf['full'])} |", f"| 最差调仓日的最大回撤 | {_pct(perf['mdd'])} |", "",
            "最大回撤取月初、月中、月末三种调仓日里最差的；只看月末调仓是 " + _pct(ctx["hist_mdd"]["core"]) + "。", "",
            "| 区间 | 收益 |", "|---|---:|"] + [f"| {k} | {_pct(v)} |" for k, v in perf["periods"].items()]
    b = ctx["boot"]
    out += ["", "## 风控规则", "",
            "历史回测最深只跌到 " + _pct(perf["mdd"]) + "，所以“-15% 触发”的规则在历史上一次也没有触发过"
            "（各规则在真实历史上的切换次数：" + "，".join(f"{k} {v[0]} 次" for k, v in ctx["hist"].items()) + "）。"
            "为了比较规则，把历史日收益按平均约 3 个月一段随机重排，生成更坏的走势：",
            f"平稳分块自助法，{b['n_paths']} 条路径，每条 {b['length'] // 252} 年，平均块长 {b['mean_block']} 个交易日，随机种子 {b['seed']}。"
            "核心和防守版（股票部分全部转入国债 ETF，债券和黄金不动）同一天成对抽取；每次切换扣 0.2% × 降仓比例 × 全部净值（实际只移动股票部分，偏保守）。", "",
            f"历史最大回撤（月末调仓、人民币、两账户合并）：核心 {_pct(ctx['hist_mdd']['core'])}，防守版 {_pct(ctx['hist_mdd']['def'])}。"
            "**防守版本身并不比核心更防守**：它保留了 35% 左右的黄金，而且按人民币计，美股账户的美债仍承担美元汇率波动。"
            "这是降仓规则帮助有限、“清零”类规则反而提高跌破 -20% 概率的最直接原因。", "",
            "改动说明：第一次运行时防守版定义为“股票 0% 的债金 1:1 组合”（一半黄金，历史最大回撤 -22.7%），改为更符合设计文档“降低股票仓位”的“股票转国债”后重跑。"
            "两次运行选中的都是“无规则”，候选规则和选法没有改动。改正后的防守版回撤（见上）仍比核心深。", "",
            "| 规则 | 说明 | 跌破 -20% 概率 | 跌破 -15% 概率 | 中位年化 | 最差 5% 年化 | 中位最大回撤 | 最差 5% 回撤 | 平均切换次数 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, r in rules.iterrows():
        mark = "**" if name == pick else ""
        out.append(f"| {mark}{name}{mark} | {RULE_TEXT.get(name, '')} | {_pct(r.p_breach20)} | {_pct(r.p_breach15)} | "
                   f"{_pct(r.median_cagr)} | {_pct(r.p5_cagr)} | {_pct(r.median_mdd)} | {_pct(r.p5_mdd)} | {r.mean_switches:.1f} |")
    out += ["", render_rules(rules, pick, DECISION), ""]
    out += ["另外，核心本身已有 10 个月均线把下跌中的股票转进国债，额外的降仓规则重复了这一步。", "",
            "实盘执行：每天收盘后，按两个账户的市值（换算成人民币）算合并净值，**按份额（时间加权）计算**，追加或取出资金不改变净值，"
            "否则入金会掩盖真实回撤；再和历史最高点比较。" +
            ("回撤到 -15% 时，第二个交易日在两个账户里同时执行降仓；恢复条件满足后的第二个交易日恢复到目标配置。" if pick != "无规则" else
             "回撤到 -15% 时发出复盘提醒，不自动交易；你可以在那时决定是否临时执行备选规则。") + "P6 会把这一步做成自动提醒。", "",
            "## 过渡方案", "",
            "从现有持仓调到本月目标。两种执行方式由你选：一次性调完，或分 3 个月每月执行三分之一。"
            "美股按整股计算（不假设可以买碎股），A股按 100 股一手；成本含佣金、滑点、个股卖出印花税。", ""]
    for label, o in ctx["orders"].items():
        ccy = ctx["accounts"][label]["ccy"]
        acc = ctx["accounts"][label]
        stale = "⚠️ 价格可能过期，下单前请重跑本报告。" if acc.get("stale") else ""
        out += [f"### {label}：一次性（价格日期 {acc['price_date']:%Y-%m-%d}）{stale}", ""] + _orders_md(o, ccy)
        out += ["", f"合计成本 {o.cost.sum():,.2f} {ccy}。", "", f"### {label}：分 3 个月", "",
                "只有第 1 期可以直接执行。第 2、3 期按今天的价格和本月信号估算，**仅供参考**：每月按新信号和新价格重跑本报告再下单。"
                "每期先卖后买，买单不超过当期可用现金。", ""]
        for k, part in enumerate(ctx["tranches"][label], 1):
            out += [f"第 {k} 个月：", ""] + _orders_md(part, ccy) + [""]
    out += ["## 税务字段（澳洲资本利得税）", "",
            "只列出计算需要的数字，不算税额：税额取决于你的税务居民身份和税率，请咨询注册税务师。"
            "持有满 12 个月（买入日和卖出日不计）的盈利可享 50% 折扣；亏损可以抵扣盈利。“待补”需要你在 `config/holdings.csv` 填买入成本和日期。", "",
            "| 持仓 | 股数 | 现价 | 成本价 | 浮动盈亏 | 已持有天数 | 可享 50% 折扣 |", "|---|---:|---:|---:|---:|---:|:-:|"]
    for r in ctx["tax"].itertuples():
        g = r.gain if isinstance(r.gain, str) else f"{r.gain:,.2f}"
        de = r.discount_eligible if isinstance(r.discount_eligible, str) else ("是" if r.discount_eligible else "否")
        out.append(f"| {r.symbol} {NAMES.get(r.symbol, '')} | {int(r.shares)} | {r.price:,.2f} | {r.cost_basis} | {g} | {r.held_days} | {de} |")
    out += ["", "## 每月操作", "",
            "1. 每月最后一个交易日收盘后，系统更新数据、计算 10 个月均线信号，生成两个账户的调仓单（P6 自动化）。",
            "2. 下一个交易日按调仓单下单。新增资金优先买入低于目标权重的资产，尽量少卖。",
            ("3. 每天收盘后检查合并回撤（按份额计）；到 -15% 执行风控规则。" if pick != "无规则" else
             "3. 每天收盘后检查合并回撤（按份额计）；到 -15% 发出复盘提醒，不自动交易，由你决定是否临时降仓。"),
            ("4. 实盘回撤上限 -20%：规则的目的是在那之前就有动作。" if pick != "无规则" else
             "4. 实盘回撤上限 -20%：-15% 的复盘是在那之前留出的决策点。"), "",
            "## 风险与局限", "",
            "- 回测和自助法都基于 2007 年以来的历史；自助法只能重排已经发生过的日子，不会产生历史上没有的极端情况。",
            "- 风控规则在真实历史上没有触发过，选择完全依赖模拟；规则本身会在下跌后卖出、回升前买回不及时，代价是收益。",
            "- 合并口径按今天的账户市值加权，之后两个账户的实际比例会变化。",
            "- A股 ETF 上市前的历史用指数补齐，见 P3 报告。",
            "- 年化收益是历史值，不是预期；样本外只有 2020 年以后约 7 年。", "",
            "## 下一步（P6）", "",
            "每月自动生成调仓单（中文 Markdown + CSV）、每日回撤监控、美股接 moomoo 模拟盘，影子盘记录至少 3 个月。", ""]
    return "\n".join(out)


def main() -> int:
    import warnings
    # 只屏蔽库的弃用提示；“更新失败、使用旧缓存”的警告要保留
    for cat in (FutureWarning, DeprecationWarning, pd.errors.PerformanceWarning):
        warnings.filterwarnings("ignore", category=cat)
    from quant.data.update import get_index, get_price, latest_quote
    from quant.portfolio.holdings import load_holdings

    fx = {"AUDUSD": get_price("AUDUSD", "FX", "fx"), "AUDCNY": get_price("AUDCNY", "FX", "fx")}
    run_id = new_run_id()
    w_us = p3.current_w_us(fx)
    h = load_holdings()
    navs, defs, accounts, orders, tranches, prices_all = {}, {}, {}, {}, {}, {}
    for label, (e, split, signal) in CORE.items():
        a = p3.ACCOUNTS[label]
        px, _ = p3.build_prices(a, get_price, get_index, fx)
        start = rebalance_dates(px, "end")[12]
        base = p3._base_weights(a, e, p3.SPLITS[split])
        navs[label] = p3.run_trial(px, base, signal, a, fx, start)[0]
        defs[label] = p3.run_trial(px, defensive_weights(base, a), signal, a, fx, start)[0]["end"]
        sig_date, target = target_weights(px, a, base, signal)
        hh = h[h.account == BROKER[label]]
        quotes = {s: latest_quote(s, a["market"], "stock" if s in STOCKS else "etf")
                  for s in set(target) | set(hh.symbol[hh.symbol != "CASH"])}
        prices = {s: q[1] for s, q in quotes.items()}
        price_date = min(q[0] for q in quotes.values())
        prices_all.update(prices)
        lot = {s: 100 if a["cn"] else 1 for s in prices}
        orders[label] = transition_orders(h, prices, target, BROKER[label], lot, cost_fn(label))
        tranches[label] = tranche_plan(orders[label], lot, cost_fn(label), n=3,
                                       cash0=float(hh[hh.symbol == "CASH"].shares.sum()))
        nav_local = float(hh[hh.symbol == "CASH"].shares.sum() + sum(r.shares * prices[r.symbol] for r in hh.itertuples() if r.symbol != "CASH"))
        accounts[label] = {"base": base, "sig_date": sig_date, "target": target, "ccy": a["ccy"], "nav": nav_local,
                           "last_data": px.index[-1], "price_date": price_date,
                           "stale": (pd.Timestamp(date.today()) - price_date).days > 5}

    us, cn = navs["美股账户"], navs["A股账户"]
    combs = {m: p3.combine_navs(us[m], cn[m], w_us) for m in ("end", "mid", "start")}
    comb = combs["end"]
    comb_def = p3.combine_navs(defs["美股账户"], defs["A股账户"], w_us)
    perf = {"is": cagr(comb.loc[:SPLIT]), "oos": cagr(comb.loc[SPLIT:]), "full": cagr(comb),
            "mdd": min(max_drawdown(c) for c in combs.values()), "periods": period_returns(comb),
            "window": f"{comb.index[0]:%Y-%m-%d} 至 {comb.index[-1]:%Y-%m-%d}"}
    core_r, def_r = comb.pct_change().dropna(), comb_def.pct_change().dropna()
    hist = {}
    for rule in RULES:
        nav, n = overlay(core_r, def_r, rule)
        hist[rule.name] = (n, max_drawdown(nav))
    table = evaluate_rules(core_r, def_r, RULES, BOOT["n_paths"], BOOT["length"], BOOT["mean_block"], BOOT["seed"])
    pick = pick_rule(table)
    for name, r in table.iterrows():
        log_trial({"name": f"P5风控｜{name}", "phase": "P5", "run_id": run_id, **r.to_dict(), "hist_switches": hist[name][0],
                   "picked": name == pick})
    log_trial({"name": "P5核心合并", "phase": "P5", "run_id": run_id, "is_cagr": perf["is"], "oos_cagr": perf["oos"],
               "full_cagr": perf["full"], "mdd_worst": perf["mdd"], "w_us": w_us, "mdd_ok": perf["mdd"] >= MDD_LIMIT})

    as_of = date.today()
    ctx = {"as_of": as_of, "w_us": w_us, "accounts": accounts, "perf": perf, "rules": table, "pick": pick, "hist": hist,
           "boot": BOOT, "orders": orders,
           "hist_mdd": {"core": max_drawdown(comb), "def": max_drawdown(comb_def)}, "tranches": tranches, "tax": tax_fields(h, prices_all, pd.Timestamp(as_of))}
    path = Path("reports") / f"P5-最终方案-{as_of}.md"
    path.write_text(render(ctx))
    print(f"已生成：{path}")
    print("选中规则：", pick, "；合并最差回撤", f"{perf['mdd']:.3f}", "；样本外", f"{perf['oos']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
