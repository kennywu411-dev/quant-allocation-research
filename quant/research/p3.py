"""P3 核心配置实验：python -m quant.research.p3"""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant.backtest import costs
from quant.backtest.engine import run_backtest
from quant.backtest.strategies import rebalance_dates, static_mix, trend_mix
from quant.fx import to_base
from quant.portfolio.checkup import fill_with_proxy
from quant.metrics import cagr, drawdown, max_drawdown
from quant.research.gates import MDD_LIMIT, evaluate, period_returns
from quant.research.registry import log_trial, new_run_id

EQUITY = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
SPLITS = {"债金2比1": (2 / 3, 1 / 3), "债金1比1": (0.5, 0.5)}
SIGNALS = ["static", "sma10_bond", "sma10_cash", "mom_bond", "mom_cash"]
# 回撤和收益的计量货币：用户 2026-10-31 决定按人民币计（这笔钱将来主要花人民币）
BASE = "CNY"
BASE_NAME = {"CNY": "人民币", "AUD": "澳元"}[BASE]
ACCOUNTS = {
    "美股账户": dict(ccy="USD", market="US", eq=["SPY"], bond=["IEF", "TLT"], gold=["GLD"], safe="IEF",
                 cost=costs.us_etf, init=10_000.0, cn=False),
    "A股账户": dict(ccy="CNY", market="CN", eq=["510300", "510880"], bond=["511010"], gold=["518880"], safe="511010",
                 cost=costs.cn_etf, init=100_000.0, cn=True,
                 proxy={"510300": ("index", "sh000300"), "510880": ("index", "sh000015"),
                        "511010": ("index", "sh000012"), "518880": ("gold_cny", "GLD")}),
}
DISCLAIMER = "> 声明：本报告不是投资建议，回测结果不代表未来收益。作者不是持牌金融顾问。"


def account_values(h: pd.DataFrame, vals: pd.Series) -> tuple[float, float]:
    """按持仓表的 market 列把市值分到美股账户和 A股账户（比例与计量货币无关）。"""
    market = {("CASH_" + r.ccy if r.symbol == "CASH" else r.symbol): r.market for r in h.itertuples()}
    us = float(sum(v for k, v in vals.items() if market.get(k) == "US"))
    return us, float(vals.sum() - us)


def align_modes(by_mode: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """三种调仓日统一从 end 模式的起点开始，保证比较的是同一段时间。"""
    s0 = by_mode["end"].index[0]
    return {k: v.loc[s0:] for k, v in by_mode.items()}


def margin_note(mdd_worst: float) -> str:
    gap = mdd_worst - MDD_LIMIT
    if 0 <= gap < 0.02:
        return (f"⚠️ 余量很小：最差回撤 {mdd_worst * 100:.1f}%，离 -15% 只差 {gap * 100:.1f} 个百分点，"
                "实盘中很容易被突破，需要配合 -15% 触发的风控规则（P5）。")
    return ""


ELIGIBLE_GATES = ["g_oos", "g_cost2", "spread_ok", "g_period"]


def eligible(res: pd.DataFrame) -> pd.Series:
    """账户级门槛（不含回撤）：样本外、成本×2、调仓日差、分时段；趋势方案还须胜过同权重静态方案。"""
    ok = res[ELIGIBLE_GATES].astype(bool).all(axis=1)
    trend = res.signal != "static"
    return ok & (~trend | res.g_vs_base.fillna(False).astype(bool))


def combine_navs(us: pd.Series, cn: pd.Series, w_us: float) -> pd.Series:
    """两个账户按初始市值加权、之后各自独立运行（不跨账户调拨）的合并净值，起点为 1。"""
    start = max(us.index[0], cn.index[0])
    df = pd.DataFrame({"us": us, "cn": cn}).sort_index().ffill().loc[start:].dropna()
    return w_us * df.us / df.us.iloc[0] + (1 - w_us) * df.cn / df.cn.iloc[0]


def select_pair(us_res: pd.DataFrame, cn_res: pd.DataFrame, navs_us: dict, navs_cn: dict, w_us: float,
                split: str = "2019-12-31", mdd_limit: float = MDD_LIMIT) -> tuple[tuple[str, str] | None, pd.DataFrame]:
    """在两个账户各自合格的方案里两两配对；合并回撤（三种调仓日取最差）≥ mdd_limit 的里面按样本内合并 CAGR 选最高。"""
    rows = []
    for u in us_res[us_res.eligible].name:
        for c in cn_res[cn_res.eligible].name:
            combs = {m: combine_navs(navs_us[u][m], navs_cn[c][m], w_us) for m in ("end", "mid", "start")}
            end = combs["end"]
            rows.append({"us": u, "cn": c, "is_cagr": cagr(end.loc[:split]), "oos_cagr": cagr(end.loc[split:]),
                         "full_cagr": cagr(end), "mdd_worst": min(max_drawdown(s) for s in combs.values())})
    table = pd.DataFrame(rows, columns=["us", "cn", "is_cagr", "oos_cagr", "full_cagr", "mdd_worst"])
    ok = table[table.mdd_worst >= mdd_limit]
    if ok.empty:
        return None, table
    best = ok.sort_values("is_cagr", ascending=False).iloc[0]
    return (best.us, best.cn), table


def gold_cny(gld: pd.Series, fx: dict) -> pd.Series:
    """美元金价换成人民币：1 美元 = AUDCNY / AUDUSD 人民币，汇率只向前填充。"""
    usdcny = (fx["AUDCNY"] / fx["AUDUSD"]).dropna()
    rate = usdcny.reindex(usdcny.index.union(gld.index)).ffill().reindex(gld.index)
    return (gld * rate).dropna()


PROXY_NAMES = {"sh000300": "沪深300指数", "sh000015": "上证红利指数", "sh000012": "上证国债指数", "GLD": "GLD×美元兑人民币",
               "H20269": "中证红利低波全收益指数", "H00300": "沪深300全收益指数",
               "6_Portfolios_ME_Prior_12_2_daily:BIG HiPRIOR": "Ken French 大盘高动量组合",
               "6_Portfolios_ME_OP_2x3_daily:BIG HiOP": "Ken French 大盘高盈利组合",
               "6_Portfolios_2x3_daily:BIG HiBM": "Ken French 大盘高账面市值比组合",
               "F-F_Research_Data_Factors_daily:MKT": "Ken French 美股全市场",
               "SPY": "2 倍 SPY 合成序列", "QQQ": "2 倍 QQQ 合成序列", "sz399006": "创业板指", "000852": "中证1000 指数"}


def build_prices(a: dict, get_price, get_index, fx: dict, getters: dict | None = None) -> tuple[pd.DataFrame, list[str]]:
    """取账户资产价格；ETF 上市前的历史用 a['proxy'] 指定的代理按收益补齐。
    getters 可按代理种类提供取数函数；a['fee'] 给出年费率时，代理段每日收益先扣 费率/252。"""
    series, notes = {}, []
    getters = getters or {}
    for s in a["eq"] + a["bond"] + a["gold"]:
        if s in a.get("synthetic", {}):  # 纯代理资产：没有真实 ETF，整段用代理收益，按年费率扣减
            kind, code, fee = a["synthetic"][s]
            proxy = getters[kind](code)
            series[s] = (1 + proxy.pct_change().fillna(0.0) - fee / 252).cumprod()
            notes.append(f"{s}：全段用 {PROXY_NAMES.get(code, code)}（{code}）的收益，每年扣 {fee * 100:.2f}% 交易成本")
            continue
        etf = get_price(s, a["market"], "etf")
        if s in a.get("proxy", {}):
            kind, code = a["proxy"][s]
            if kind in getters:
                proxy = getters[kind](code)
            elif kind == "index":
                proxy = get_index(code)
            elif kind == "gold_cny":
                proxy = gold_cny(get_price(code, "US", "etf"), fx)
            else:
                raise ValueError(f"{s}：代理种类 {kind} 没有提供取数函数（getters）")
            fee = a.get("fee", {}).get(s, 0.0)
            if fee:
                proxy = (1 + proxy.pct_change().fillna(0.0) - fee / 252).cumprod()
            filled, cut = fill_with_proxy(etf, proxy)
            if cut is not None:
                fee_txt = f"，每年扣费 {fee * 100:.2f}%" if fee else ""
                notes.append(f"{s}：{filled.index[0]:%Y-%m-%d} 至 {cut:%Y-%m-%d} 用 {PROXY_NAMES.get(code, code)}（{code}）的收益补齐{fee_txt}")
                etf = filled
        series[s] = etf
    px = pd.DataFrame(series).sort_index()
    return px.loc[max(px[c].first_valid_index() for c in px):], notes


def _base_weights(a: dict, e: float, split: tuple[float, float]) -> dict[str, float]:
    w = {s: e / len(a["eq"]) for s in a["eq"]}
    w.update({s: (1 - e) * split[0] / len(a["bond"]) for s in a["bond"]})
    w.update({s: (1 - e) * split[1] / len(a["gold"]) for s in a["gold"]})
    return w


def _weights(px, base, signal, a, dates):
    if signal == "static":
        return static_mix(px, base, dates)
    kind, dest = signal.split("_")
    sig_px = px
    if a.get("signal_series"):  # 杠杆 ETF 用对应 1 倍指数的价格判断信号，避免杠杆损耗让信号失真
        sig_px = px.copy()
        for s, ser in a["signal_series"].items():
            sig_px[s] = ser.reindex(px.index).ffill()
    return trend_mix(sig_px, base, a["eq"] + a["gold"], a["safe"] if dest == "bond" else None, kind, dates)


def _run(px, w, a, cost_k, fx):
    """返回（基准货币净值, 本币净值）。"""
    cm = {s: costs.scaled(a["cost"](), cost_k) for s in px}
    nav = run_backtest(px, w, cm, a["init"], cn_rules=a["cn"], fractional=a.get("fractional", False)).nav
    nav = nav.loc[nav.index[nav.index > w.index[0]][0]:]
    return to_base(nav, a["ccy"], fx, BASE), nav


def run_trial(px: pd.DataFrame, base: dict, signal: str, a: dict, fx: dict, common_start: pd.Timestamp):
    """单个试验：三种调仓日的基准货币净值（起点对齐）、成本×2 净值、本币净值。"""
    by_mode, local = {}, None
    for mode in ("end", "mid", "start"):
        w = _weights(px, base, signal, a, rebalance_dates(px, mode))
        w = w[w.index >= common_start - pd.offsets.MonthBegin(1)]
        by_mode[mode], loc = _run(px, w, a, 1.0, fx)
        local = loc if mode == "end" else local
    by_mode = align_modes(by_mode)
    w_end = _weights(px, base, signal, a, rebalance_dates(px, "end"))
    w_end = w_end[w_end.index >= common_start - pd.offsets.MonthBegin(1)]
    cost2 = _run(px, w_end, a, 2.0, fx)[0].loc[by_mode["end"].index[0]:]
    return by_mode, cost2, local


def current_w_us(fx: dict) -> float:
    """美股账户占两个账户当前总市值的比例（按最新实际价格和汇率）。"""
    from quant.data.update import latest_price
    from quant.portfolio.checkup import current_values_aud
    from quant.portfolio.holdings import load_holdings

    h = load_holdings()
    last = {s: latest_price(s, m, "stock") for s, m in zip(h.symbol, h.market) if s != "CASH"}
    fx_last = {"USD": float(fx["AUDUSD"].iloc[-1]), "CNY": float(fx["AUDCNY"].iloc[-1]), "AUD": 1.0}
    us_v, cn_v = account_values(h, current_values_aud(h, last, fx_last))
    return us_v / (us_v + cn_v)


def run_account(label: str, a: dict, fx: dict, get_price, run_id: str = "", get_index=None,
                phase: str = "P3") -> tuple[pd.DataFrame, dict, list[str]]:
    px, notes = build_prices(a, get_price, get_index, fx)
    # 所有试验从同一天开始：动量信号需要 13 个月末采样点
    common_start = rebalance_dates(px, "end")[12]
    rows, navs = [], {}
    for e in EQUITY:
        for sname, split in SPLITS.items():
            base = _base_weights(a, e, split)
            baseline = None
            for signal in SIGNALS:
                name = f"{label}｜股{int(e * 100)}%｜{sname}｜{signal}"
                by_mode, cost2, local = run_trial(px, base, signal, a, fx, common_start)
                r = evaluate(by_mode, cost2, baseline=None if signal == "static" else baseline)
                dd = drawdown(by_mode["end"])
                trough = dd.idxmin()
                r.update(local_mdd=max_drawdown(local.loc[by_mode["end"].index[0]:]),
                         aud_peak=f"{by_mode['end'].loc[:trough].idxmax():%Y-%m}", aud_trough=f"{trough:%Y-%m}")
                if signal == "static":
                    baseline = by_mode["end"]
                row = {"name": name, "account": label, "equity": e, "split": sname, "signal": signal,
                       "weights": ";".join(f"{k}={v:.3f}" for k, v in base.items()), **r}
                log_trial({**row, "phase": phase, "run_id": run_id})
                rows.append(row)
                navs[name] = by_mode
    res = pd.DataFrame(rows)
    res["eligible"] = eligible(res)
    return res, navs, notes


def _pct(x) -> str:
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:.1f}%"


def _ok(x) -> str:
    return "—" if x is None else ("✓" if x else "✗")


def render(per_account: dict, comb: dict, as_of: date, start_info: dict, data_notes: list[str] | None = None) -> str:
    out = [f"# P3 核心配置报告（{as_of:%Y-%m-%d}）", "", DISCLAIMER, "",
           "## 方法", "",
           f"- 两个账户各自独立回测（本币），再换算成{BASE_NAME}。成本按设计文档第 4 节，整手成交，A股账户开启涨跌停、停牌、T+1 规则。",
           "- 每个账户 80 个试验：股票占比 0%–70%（8 档）× 债金比例 2 种 × 信号 5 种（静态、10 月均线转债/转现金、3-6-9-12 月动量转债/转现金）。"
           "所有试验记在 `research/trials.csv`，带运行编号。",
           "- 样本内：截至 2019-12-31；样本外：2020 年以后，只用于检验，不参与排名。",
           "- **账户级门槛**（每个账户分别检验）：样本外 CAGR > 0 且 ≥ 样本内一半；成本 ×2 后仍盈利；月初/月中/月末调仓 CAGR 差 ≤ 2 个百分点；"
           "去掉最好一年后仍盈利；趋势方案还须比同权重静态方案回撤少 ≥ 3 个百分点、收益少 ≤ 2 个百分点。",
           f"- **计量货币：{BASE_NAME}**（你 2026-10-31 的决定，这笔钱将来主要花{BASE_NAME}），收益和回撤都按{BASE_NAME}计。",
           "- **回撤门槛只看两个账户合并**（你 2026-10-30 的决定）：按当前两个账户的市值加权、账户之间不调拨，"
           "三种调仓日里最差的合并最大回撤 ≥ -15%。",
           "- 选法：两个账户各自合格的方案两两配对，在满足合并回撤的配对里按**样本内**合并 CAGR 选最高。", ""]
    if data_notes:
        out += ["**A股 ETF 上市前的历史用指数补齐**（设计文档第 7 节）：", ""] + [f"- {n}" for n in data_notes]
        out += ["- 指数是价格指数，不含分红：补齐段的收益偏低（红利指数尤其明显，股息率常在 4%–5%），回撤数字偏保守；"
                "国债指数和换算金价与 ETF 也有跟踪误差。", ""]
    for label, d in per_account.items():
        res = d["results"]
        out += [f"## {label}", "", f"回测区间（{BASE_NAME}口径）：{start_info[label]}。80 个试验中通过账户级门槛 {int(res.eligible.sum())} 个"
                "（单账户回撤只列出，不作门槛）。", "",
                "样本内 CAGR 前 10 的试验：", "",
                "| 试验 | 样本内 | 样本外 | 单账户最差回撤 | 本币回撤 | 成本×2 | 样本外门槛 | 调仓日差≤2pp | 分时段 | 比静态 | 账户级合格 |",
                "|---|---:|---:|---:|---:|---:|:-:|:-:|:-:|:-:|:-:|"]
        for r in res.sort_values("is_cagr", ascending=False).head(10).itertuples():
            out.append(f"| {r.name.split('｜', 1)[1]} | {_pct(r.is_cagr)} | {_pct(r.oos_cagr)} | {_pct(r.mdd_worst)} | "
                       f"{_pct(r.local_mdd)} | {_pct(r.cost2_cagr)} | {_ok(r.g_oos)} | {_ok(r.spread_ok)} | {_ok(r.g_period)} | "
                       f"{_ok(r.g_vs_base)} | {_ok(r.eligible)} |")
        out.append("")

    out += [f"## 合并选择（{BASE_NAME}）", "",
            f"权重：美股账户 {_pct(comb['w_us'])}、A股账户 {_pct(comb['w_cn'])}（按当前持仓市值）。"
            f"合并区间 {comb['window']}。共评估 {len(comb['table'])} 个配对，满足合并回撤的 {comb['n_ok']} 个。", ""]
    pick = comb["pick"]
    if pick is None:
        near = comb["table"].sort_values("mdd_worst", ascending=False).head(3)
        out += ["**结果：无可用核心配置**", "", "最接近通过的 3 个配对：", ""]
        out += [f"- 美股 `{r.us.split('｜', 1)[1]}` + A股 `{r.cn.split('｜', 1)[1]}`：合并最差回撤 {_pct(r.mdd_worst)}，"
                f"全期 CAGR {_pct(r.full_cagr)}" for r in near.itertuples()]
        out.append("")
    else:
        r = comb["row"]
        out += ["**结果：找到满足条件的核心配置**", "",
                f"| 账户 | 选中方案 | 基础权重 | 单账户最差回撤（{BASE_NAME}） |", "|---|---|---|---:|"]
        for label, name in zip(per_account, pick):
            a = per_account[label]["results"].set_index("name").loc[name]
            out.append(f"| {label} | {name.split('｜', 1)[1]} | {a['weights'].replace(';', '，')} | {_pct(a.mdd_worst)} |")
        out += ["", "| 合并指标 | 数值 |", "|---|---:|",
                f"| 样本内 CAGR | {_pct(r.is_cagr)} |", f"| 样本外 CAGR | {_pct(r.oos_cagr)} |",
                f"| 全期 CAGR | {_pct(r.full_cagr)} |", f"| 最差调仓日的合并最大回撤 | {_pct(r.mdd_worst)} |"]
        note = margin_note(r.mdd_worst)
        out += (["", note] if note else [])
        out += ["", "合并净值分时段表现：", "", "| 区间 | 收益 |", "|---|---:|"]
        out += [f"| {k} | {_pct(v)} |" for k, v in comb["periods"].items()]
        out.append("")
    top = comb["table"][comb["table"].mdd_worst >= MDD_LIMIT].sort_values("is_cagr", ascending=False).head(5)
    if len(top):
        out += ["满足合并回撤、样本内合并 CAGR 前 5 的配对：", "", "| 美股方案 | A股方案 | 样本内 | 样本外 | 合并最差回撤 |", "|---|---|---:|---:|---:|"]
        out += [f"| {r.us.split('｜', 1)[1]} | {r.cn.split('｜', 1)[1]} | {_pct(r.is_cagr)} | {_pct(r.oos_cagr)} | {_pct(r.mdd_worst)} |"
                for r in top.itertuples()]
        out.append("")
    out += ["## 局限", "",
            f"- 回测区间：美股账户 {start_info['美股账户']}；A股账户 {start_info['A股账户']}。"
            f"合并结果覆盖 {comb['window']}。",
            "- 样本外只有 2020 年以后约 7 年，统计上很短。",
            "- 红利部分用 510880（上证红利）代替红利低波 512890。",
            f"- 配对搜索相当于又做了 {len(comb['table'])} 次比较，选出的最优配对有选择偏差；按样本内排名只能减轻，不能消除。",
            "- 两个账户的权重按今天的市值固定为起点，之后不跨账户再平衡；实际资金比例变化会改变合并回撤。",
            "- 回测不代表未来；2022 年股债同跌这类情形会再次出现。", ""]
    return "\n".join(out)


def main() -> int:
    import warnings
    warnings.filterwarnings("ignore")
    from quant.data.update import get_index, get_price

    fx = {"AUDUSD": get_price("AUDUSD", "FX", "fx"), "AUDCNY": get_price("AUDCNY", "FX", "fx")}
    run_id = new_run_id()
    per_account, start_info, all_navs, data_notes = {}, {}, {}, []
    for label, a in ACCOUNTS.items():
        res, navs, notes = run_account(label, a, fx, get_price, run_id, get_index)
        data_notes += notes
        any_nav = next(iter(navs.values()))["end"]
        start_info[label] = f"{any_nav.index[0]:%Y-%m-%d} 至 {any_nav.index[-1]:%Y-%m-%d}"
        per_account[label], all_navs[label] = {"results": res}, navs

    w_us = current_w_us(fx)

    pick, table = select_pair(per_account["美股账户"]["results"], per_account["A股账户"]["results"],
                              all_navs["美股账户"], all_navs["A股账户"], w_us)
    for r in table.itertuples():
        log_trial({"name": f"配对｜{r.us}｜{r.cn}", "phase": "P3-合并", "run_id": run_id, "is_cagr": r.is_cagr,
                   "oos_cagr": r.oos_cagr, "full_cagr": r.full_cagr, "mdd_worst": r.mdd_worst, "w_us": w_us})
    comb = {"pick": pick, "table": table, "w_us": w_us, "w_cn": 1 - w_us,
            "n_ok": int((table.mdd_worst >= MDD_LIMIT).sum()) if len(table) else 0, "window": "—", "periods": {}}
    if len(table):
        u0, c0 = table.iloc[0].us, table.iloc[0].cn
        c = combine_navs(all_navs["美股账户"][u0]["end"], all_navs["A股账户"][c0]["end"], w_us)
        comb["window"] = f"{c.index[0]:%Y-%m-%d} 至 {c.index[-1]:%Y-%m-%d}"
    if pick:
        nav = combine_navs(all_navs["美股账户"][pick[0]]["end"], all_navs["A股账户"][pick[1]]["end"], w_us)
        comb["periods"] = period_returns(nav)
        comb["row"] = table[(table.us == pick[0]) & (table.cn == pick[1])].iloc[0]

    as_of = date.today()
    path = Path("reports") / f"P3-核心配置-{as_of}.md"
    path.write_text(render(per_account, comb, as_of, start_info, data_notes))
    print(f"已生成：{path}")
    print("选中：", pick)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
