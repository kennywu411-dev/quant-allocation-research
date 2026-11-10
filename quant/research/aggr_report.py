"""激进版方案报告：python -m quant.research.aggr_report（先跑 quant.research.aggr 和 quant.research.mom_stocks）"""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant.research.aggr import AGGR_MDD, PICK_PATH

MOM_PATH = Path("research/mom_bias.json")
TIGHT = 0.02
DISCLAIMER = "> 声明：本报告不是投资建议，回测结果不代表未来收益。作者不是持牌金融顾问。是否采用、何时执行由你决定。"


def _p(x) -> str:
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:.1f}%"


def _short(name: str) -> str:
    return name.split("｜", 1)[1] if name.startswith("美股账户｜") else name.replace("P3｜A股账户｜", "")


def render(ctx: dict) -> str:
    perf, cur, boot = ctx["perf"], ctx["current"], ctx["boot"]
    mdd = ctx.get("mdd", AGGR_MDD)
    cap, deep = f"{mdd * 100:.0f}%", f"{(mdd - 0.10) * 100:.0f}%"
    cur_name = ctx.get("current_name", "现行（P5）")
    lev_pick = any(k in ctx["pick"][0] for k in ("QLD", "SSO"))
    margin = perf["mdd"] - mdd
    out = [f"# 激进版方案（{ctx['as_of']}）", "",
           f"**一句话**：在合并回撤 ≥ {cap} 的约束下，按预先固定的选法选中 **美股 {_short(ctx['pick'][0])} ＋ A股 {_short(ctx['pick'][1])}**："
           f"回测全期年化 {_p(perf['full'])}（{cur_name} {_p(cur['full'])}），最差合并回撤 {_p(perf['mdd'])}（{cur_name} {_p(cur['mdd'])}）。"
           + ("收益来自 2 倍杠杆纳斯达克 100，代价是回撤接近腰斩。" if lev_pick else "收益提高的代价是回撤翻倍，而且这个方案的大部分收益来自纳斯达克 100。"), ""]
    if margin < TIGHT:
        out += [f"**几乎贴线**：最差回撤离 {cap} 上限只差 {margin * 100:.1f} 个百分点；"
                f"下面的自助法显示，未来 10 年跌破 {cap} 的概率约 {_p(boot['p_cap'])}。", ""]
    if ctx.get("expanded"):
        out += ["**候选扩充**：原计划 A股只有股票 80–100% 三档，-30% 上限下任何配对都压不进；A股候选并入了 P3 已登记的 80 个方案。"
                f"这是看到结果之后的扩充，满足约束的配对共 {ctx['n_ok']} 个，选法本身没变，但样本外结果要打折看。"
                + ("说得直白些：**A股的激进候选都没有用上**，选中的 A股部分就是 P3 的防守配置，“激进”全部体现在美股账户。"
                   if ctx["pick"][1].startswith("P3｜") else ""), ""]
    if ctx.get("close_calls"):
        out += [ctx["close_calls"], ""]
    out += ["## 目标配置", ""]
    for label, x in ctx["accounts"].items():
        out += [f"### {label}（信号日 {x['sig_date']:%Y-%m-%d}）", "",
                "| 资产 | 目标权重 |", "|---|---|", *[f"| {s} | {w * 100:.1f}% |" for s, w in x["target"].items()], ""]
    out += ["## 与现行方案对比", "", f"合并、人民币计、已扣成本；区间 {perf['window']}；美股账户占 {ctx['w_us'] * 100:.1f}%。", "",
            f"| | 新方案 | {cur_name} |", "|---|---|---|",
            f"| 样本内年化（至 2019） | {_p(perf['is'])} | {_p(cur['is'])} |",
            f"| 样本外年化（2020 起） | {_p(perf['oos'])} | {_p(cur['oos'])} |",
            f"| 全期年化 | {_p(perf['full'])} | {_p(cur['full'])} |",
            f"| 最差合并回撤 | {_p(perf['mdd'])} | {_p(cur['mdd'])} |"]
    note_cur = ["", ctx.get("current_note", "现行方案的数字与 P5 报告（最差 -14.2%）略有差别：两账户权重按今天的市值重算（美股占比上升），且数据统一截到 French 动量数据的最后一天。")]
    out += [f"| {k} | {_p(v)} | {_p(cur['periods'].get(k))} |" for k, v in perf["periods"].items()]
    worst = sorted(perf["years"].items(), key=lambda kv: kv[1])[:3]
    out += ["", "最差的三个自然年（新方案 / 现行）：" + "；".join(
        f"{y} 年 {_p(v)} / {_p(cur['years'].get(y))}" for y, v in worst), "",
        "样本外明显高于样本内，主要是 2020 年以后纳斯达克 100 的大牛市，不能当成常态。", *note_cur, ""]
    if ctx.get("sens"):
        out += ["### 美股占比敏感性", "",
                f"两账户的权重按今天的市值算（美股 {ctx['w_us'] * 100:.1f}%）。美股占比一变，结果就跟着变：", "",
                f"| 美股占比 | 全期年化 | 最差合并回撤 | 满足 {cap} |", "|---|---|---|---|"]
        out += [f"| {w * 100:.0f}% | {_p(c)} | {_p(m)} | {'是' if m >= mdd else '否'} |" for w, (c, m) in sorted(ctx["sens"].items())]
        out += ["", f"美股账户入金、A股账户卖出个股，都会改变这个比例；比例上升到一定程度，同一方案就会突破 {cap}。", ""]
    out += ["## 自助法压力测试", "",
            f"把合并日收益按平均约 3 个月一段随机重排，生成 {boot['n_paths']} 条 {boot['length'] // 252} 年路径"
            f"（平均块长 {boot['mean_block']} 天，种子 {boot['seed']}）：", "",
            "| 指标 | 数值 |", "|---|---|",
            f"| 跌破 {cap} 的概率 | {_p(boot['p_cap'])} |", f"| 跌破 {deep} 的概率 | {_p(boot['p_deep'])} |",
            f"| 年化中位数 | {_p(boot['median_cagr'])} |", f"| 年化 5% 分位（最差 5%） | {_p(boot['p5_cagr'])} |",
            f"| 最大回撤中位数 | {_p(boot['median_mdd'])} |", ""]
    lev = ctx["lev"]
    crash = f"- 跳空风险：1987-10-19 美股单日 {_p(lev['crash_1987'] / 2)}，2 倍 ETF 当天约 {_p(lev['crash_1987'])}；月度调仓来不及反应。"
    te = ("- 2 倍 ETF 上市前的合成序列已按真实 SSO/QLD 校准（重叠期每年差 " +
          "、".join(f"{k} {v * 100:+.2f}%" for k, v in lev["te"].items()) + "）。")
    if lev_pick:
        dot = lev.get("dot_com")
        out += ["## 杠杆的风险（选中的就是 2 倍 ETF）", "",
                "- 2 倍 ETF 每天重置杠杆：涨跌来回震荡时会损耗，长期收益不等于指数的 2 倍。",
                *([f"- 回测没有覆盖 2000–2002 年科网泡沫：那段 QQQ 最大回撤 {_p(dot[0])}，每日 2 倍合成序列 {_p(dot[1])}，"
                   "按目标权重算，美股账户在那种行情下会亏掉大半，合并回撤会远超上限。"] if dot else []),
                crash, te,
                "- 带均线的杠杆方案回撤更小，但没通过“调仓日敏感性”（三个调仓日年化相差超过 2 个百分点），不能入选。", ""]
    else:
        out += ["## 杠杆候选为什么没入选", "",
                f"- 回测里年化最高的杠杆方案是 {_short(lev['best_lev'])}，但它的账户回撤 {_p(lev['best_lev_mdd'])}，和任何 A股方案配对都远超 {cap}；"
                "加上均线的杠杆方案又没通过“调仓日敏感性”（三个调仓日年化相差超过 2 个百分点）。", crash, te, ""]
    mom = ctx["mom"]
    out += ["## 个股与幸存者偏差", "",
            f"- 用今天的纳指100 + 标普100 成分股回测“每月持有动量前 15 名”：年化 {_p(mom['real_cagr'])}，"
            f"同期 French 大盘高动量组合（含退市股）{_p(mom['french_cagr'])}，差 {mom['bias'] * 100:.1f} 个百分点。"
            "这个差额主要是幸存者偏差和集中度，不是可重复的超额收益。",
            "- 激进版里的动量个股候选用的是 French 序列（无幸存者偏差），样本内年化低于纳指100 系列，所以没入选。", ""]
    out += ["## 调到目标（一次性）", ""]
    for label, x in ctx["accounts"].items():
        o = x["orders"]
        if x.get("value_override"):
            out += [f"### {label}（按你给的账户总值 {x['value_override']:,.0f} {x['ccy']}，价格日期 {x['price_date']:%Y-%m-%d}）", "",
                    "持仓文件已过期，这里只给目标股数：先卖掉表外的持仓，再买到下面的数量。", "",
                    "| 代码 | 目标权重 | 目标股数 | 参考价 | 约金额 |", "|---|---|---|---|---|"]
            out += [f"| {r.symbol} | {r.weight * 100:.1f}% | {r.shares:.0f} | {r.price:,.2f} | {r.value:,.2f} {x['ccy']} |"
                    for r in o[o.symbol != "CASH"].itertuples()]
        else:
            out += [f"### {label}（价格日期 {x['price_date']:%Y-%m-%d}）", "", "| 方向 | 代码 | 数量 | 参考价 | 金额 | 成本 |", "|---|---|---|---|---|---|"]
            out += [f"| {r.side} | {r.symbol} | {r.shares:.0f} | {r.price:,.2f} | {r.value:,.2f} {x['ccy']} | {r.cost:,.2f} |"
                    for r in o[o.symbol != "CASH"].itertuples()]
        out += ["", f"剩余现金约 {o[o.symbol == 'CASH'].value.iloc[0]:,.2f} {x['ccy']}。", ""]
    out += ["## 风险与局限", "",
            *(["- 集中：美股账户八成在 2 倍纳指（等于约 1.6 倍纳斯达克 100 敞口），一次科技股熊市就可能突破上限；合并回测从 2007 年起，没有覆盖 2000–2002 年。"]
              if lev_pick else
              ["- 集中：美股账户九成在纳斯达克 100（科技股为主），一次科技股熊市（如 2000–2002 年纳指100 跌约 80%）就可能突破上限；合并回测从 2007 年起，没有覆盖那段最惨的下跌。"]),
            "- 不带均线：选中的美股方案是静态持有，下跌时不会自动减仓；-15% 时系统只提醒复盘（你 2026-10-31 的决定仍然有效）。",
            "- 换汇与税：调仓会卖出现有持仓，盈亏可能涉及税务，请咨询注册税务师。", "",
            "## 需要你决定", "",
            "1. 是否用新方案替换现行方案（替换后每日净值、影子盘、模拟盘、月度调仓单都改按新方案运行）。",
            "2. 一次性调仓还是分 3 个月过渡。",
            f"3. 能否接受“几乎贴线”：历史最差已到 {_p(perf['mdd'])}，未来跌破 {cap} 的概率约 {_p(boot['p_cap'])}。" if margin < TIGHT else
            f"3. 回撤约束 {cap} 是否仍是你想要的。", "", DISCLAIMER, ""]
    return "\n".join(out)


def _perf(navs_us: dict, navs_cn: dict, w_us: float, end: pd.Timestamp) -> tuple[dict, pd.Series]:
    from quant.metrics import cagr, max_drawdown
    from quant.research import p3
    from quant.research.gates import period_returns
    combs = {m: p3.combine_navs(navs_us[m].loc[:end], navs_cn[m].loc[:end], w_us) for m in ("end", "mid", "start")}
    c = combs["end"]
    yr = c.resample("YE").last().pct_change().dropna()
    return ({"is": cagr(c.loc[:"2019-12-31"]), "oos": cagr(c.loc["2019-12-31":]), "full": cagr(c),
             "mdd": min(max_drawdown(s) for s in combs.values()), "periods": period_returns(c),
             "years": {d.year: float(v) for d, v in yr.items()}, "window": f"{c.index[0]:%Y-%m-%d} 至 {c.index[-1]:%Y-%m-%d}"}, c)


def boot_stats(comb: pd.Series, n_paths: int, length: int, mean_block: int, seed: int, cap: float = AGGR_MDD) -> dict:
    from quant.research.riskrule import block_bootstrap
    r = comb.pct_change().dropna().to_frame("r")
    paths = block_bootstrap(r, n_paths, length, mean_block, seed)[:, :, 0]
    nav = np.cumprod(1 + paths, axis=1)
    mdd = (nav / np.maximum.accumulate(nav, axis=1) - 1).min(axis=1)
    cg = nav[:, -1] ** (252 / length) - 1
    return {"p_cap": float((mdd < cap).mean()), "p_deep": float((mdd < cap - 0.10).mean()), "median_cagr": float(np.median(cg)),
            "p5_cagr": float(np.percentile(cg, 5)), "median_mdd": float(np.median(mdd)),
            "n_paths": n_paths, "length": length, "mean_block": mean_block, "seed": seed}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import math
    import warnings
    ap = argparse.ArgumentParser()
    ap.add_argument("--us-value", type=float, default=None, help="美股账户总值（美元）；持仓文件过期时手动给，只出目标股数")
    args = ap.parse_args(argv)
    warnings.filterwarnings("ignore")
    from quant.backtest.strategies import rebalance_dates
    from quant.data.update import get_french, get_index, get_price, latest_quote
    from quant.portfolio.holdings import load_holdings
    from quant.portfolio.transition import target_weights, transition_orders
    from quant.research import aggr, p3, p5
    from quant.research.aggr_data import SYNTH_FEE, leveraged, tracking_error

    pk = json.loads(PICK_PATH.read_text())
    us_name, cn_name = pk["pick"]
    end, w_us, mdd = pd.Timestamp(pk["end"]), pk["w_us"], pk.get("mdd", AGGR_MDD)
    from quant.data.update import get_csindex
    fx = {"AUDUSD": get_price("AUDUSD", "FX", "fx"), "AUDCNY": get_price("AUDCNY", "FX", "fx")}
    rf = get_french("F-F_Research_Data_Factors_daily", "RF").pct_change()
    getters = {"csindex": get_csindex, "french": lambda code: get_french(*code.split(":")),
               "lev": lambda code: leveraged(get_price(code, "US", "etf"), 2, SYNTH_FEE, rf)}
    _, sleeve, eq, sig = us_name.split("｜")
    e_us = int(eq.removeprefix("股").removesuffix("%")) / 100
    a_us, px_us, _ = aggr.sleeve_setup("美股账户", sleeve, get_price, get_index, fx, getters)  # 与回测网格同一套配置
    base_us = p3._base_weights(a_us, e_us, p3.SPLITS[aggr.SPLIT_NAME])
    if cn_name.startswith("P3｜"):
        _, _, eq_cn, split_cn, sig_cn = cn_name.split("｜")
        a_cn = p3.ACCOUNTS["A股账户"]
        px_cn, _ = p3.build_prices(a_cn, get_price, get_index, fx)
    else:  # 激进版 A股候选（如 512100），与回测网格同一套配置
        _, sleeve_cn, eq_cn, sig_cn = cn_name.split("｜")
        split_cn = aggr.SPLIT_NAME
        a_cn, px_cn, _ = aggr.sleeve_setup("A股账户", sleeve_cn, get_price, get_index, fx, getters)
    base_cn = p3._base_weights(a_cn, int(eq_cn.removeprefix("股").removesuffix("%")) / 100, p3.SPLITS[split_cn])
    nav_us = p3.run_trial(px_us, base_us, sig, a_us, fx, rebalance_dates(px_us, "end")[12])[0]
    nav_cn = p3.run_trial(px_cn, base_cn, sig_cn, a_cn, fx, rebalance_dates(px_cn, "end")[12])[0]
    perf, comb = _perf(nav_us, nav_cn, w_us, end)
    from quant.live import plan
    cur_navs = {}
    for label in plan.LABELS:  # 现行 = 当前实盘方案（plan.py）
        e, split, signal = plan.core(label)
        a, px = plan.build(label, get_price, get_index, fx, getters)
        cur_navs[label] = p3.run_trial(px, p3._base_weights(a, e, p3.SPLITS[split]), signal, a, fx, rebalance_dates(px, "end")[12])[0]
    current, _ = _perf(cur_navs["美股账户"], cur_navs["A股账户"], w_us, end)
    boot = boot_stats(comb, **p5.BOOT, cap=mdd)
    sens = {}
    for w in (0.45, 0.50, 0.55, 0.60):
        x, _ = _perf(nav_us, nav_cn, w, end)
        sens[w] = (x["full"], x["mdd"])
    te = {}
    for real, b in (("SSO", "SPY"), ("QLD", "QQQ")):
        r, bb = get_price(real, "US", "etf").dropna(), get_price(b, "US", "etf").dropna()
        te[real] = tracking_error(r.loc[:end], leveraged(bb.loc[r.index[0]:], 2, SYNTH_FEE, rf).loc[:end])
    mkt = get_french("F-F_Research_Data_Factors_daily", "MKT").pct_change()
    t = pd.read_csv("research/trials.csv")
    g = t[(t.phase == "AGGR") & (t.run_id == pk["run_id"]) & t.name.str.contains("SSO|QLD")]
    bl = g.sort_values("is_cagr", ascending=False).iloc[0]
    from quant.metrics import max_drawdown
    from quant.data.update import fetch_us
    qqq = fetch_us("QQQ", "1999-03-01").dropna()  # 缓存从 2002 年起，科网泡沫段单独取
    dot = (max_drawdown(qqq.loc["2000-01-01":"2003-12-31"]),
           max_drawdown(leveraged(qqq, 2, SYNTH_FEE, rf).loc["2000-01-01":"2003-12-31"]))
    lev = {"crash_1987": 2 * float(mkt.loc["1987-10-19"]), "te": te, "best_lev": bl["name"], "best_lev_mdd": float(bl.full_mdd),
           "dot_com": dot}
    ok = t[(t.phase == "AGGR-合并") & (t.run_id == pk["run_id"]) & (t.mdd_worst >= mdd)]
    n_ok = len(ok)
    top = ok.sort_values("is_cagr", ascending=False).head(5)
    close_calls = None
    if len(top) > 1 and top.is_cagr.iloc[0] - top.is_cagr.iloc[1] < 0.005:
        close_calls = (f"**选中和第二名只差 {(top.is_cagr.iloc[0] - top.is_cagr.iloc[1]) * 100:.1f} 个百分点**（样本内年化），"
                       "排名前几的配对美股部分相同、A股部分不同，A股选哪个基本是噪音；结果主要由美股方案决定。")

    h = load_holdings()
    accounts = {}
    for label, a, px, base, signal in (("美股账户", a_us, px_us, base_us, sig), ("A股账户", a_cn, px_cn, base_cn, sig_cn)):
        sig_date, target = target_weights(px, a, base, signal)
        aggr.assert_tradable(target, a)
        hh = h[h.account == p5.BROKER[label]]
        quotes = {s: latest_quote(s, a["market"], "stock" if s in p5.STOCKS else "etf")
                  for s in set(target) | set(hh.symbol[hh.symbol != "CASH"])}
        prices = {s: q[1] for s, q in quotes.items()}
        lot = {s: 100 if a["cn"] else 1 for s in prices}
        accounts[label] = {"target": target, "sig_date": sig_date, "ccy": a["ccy"],
                           "orders": transition_orders(h, prices, target, p5.BROKER[label], lot, p5.cost_fn(label)),
                           "price_date": min(q[0] for q in quotes.values())}
        if label == "美股账户" and args.us_value:
            rows = [{"symbol": s_, "weight": w_, "shares": math.floor(args.us_value * w_ / prices[s_]), "price": prices[s_]}
                    for s_, w_ in target.items() if w_ > 0]
            for r_ in rows:
                r_["value"] = r_["shares"] * r_["price"]
            rows.append({"symbol": "CASH", "weight": 0.0, "shares": 0, "price": 1.0, "value": args.us_value - sum(r_["value"] for r_ in rows)})
            accounts[label].update(orders=pd.DataFrame(rows), value_override=args.us_value)
    ctx = {"as_of": f"{date.today()}", "pick": (us_name, cn_name), "w_us": w_us, "perf": perf, "current": current,
           "boot": boot, "accounts": accounts, "lev": lev, "mom": json.loads(MOM_PATH.read_text()), "n_ok": n_ok,
           "expanded": True, "sens": sens, "mdd": mdd, "close_calls": close_calls,
           "current_name": f"现行（{plan.NAME}）", "current_note": f"现行 = 当前实盘方案（{plan.NAME}，{plan.SINCE} 起），按今天的美股占比重算。"}
    path = Path("reports") / f"激进版-方案-{date.today()}.md"
    path.write_text(render(ctx))
    print("已生成：", path, {k: perf[k] for k in ("is", "oos", "full", "mdd")}, boot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
