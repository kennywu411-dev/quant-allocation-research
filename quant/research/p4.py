"""P4 卫星检验：python -m quant.research.p4

第一层：因子证据（长历史，候选相对基准的 alpha t 值与通缩夏普）。
第二层：落地检验（把 P3 核心的股票部分按比例换成候选，复用 P3 的门槛，并要求比原核心更好）。
"""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant.backtest.strategies import rebalance_dates
from quant.metrics import cagr, max_drawdown
from quant.research import p3
from quant.research.gates import MDD_LIMIT, evaluate, period_returns
from quant.research.registry import log_trial, new_run_id
from quant.research.stats import alpha_t, deflated_sharpe, monthly_returns

SPLIT = "2019-12-31"
T_MIN, DSR_MIN = 2.5, 0.95
FRACS = [0.25, 0.5, 1.0]
# P3 选中的核心（reports/P3-核心配置-2026-10-31.md，人民币口径）
CORE = {"美股账户": (0.6, "债金1比1", "sma10_bond"), "A股账户": (0.3, "债金1比1", "sma10_bond")}

FF_MOM = "6_Portfolios_ME_Prior_12_2_daily:BIG HiPRIOR"
FF_QUAL = "6_Portfolios_ME_OP_2x3_daily:BIG HiOP"
FF_VAL = "6_Portfolios_2x3_daily:BIG HiBM"
FF_MKT = "F-F_Research_Data_Factors_daily:MKT"
US_SATS = {"MTUM": FF_MOM, "QUAL": FF_QUAL, "VLUE": FF_VAL}
FEES = {"MTUM": 0.0015, "QUAL": 0.0015, "VLUE": 0.0015, "SPY": 0.000945, "512890": 0.006, "510300": 0.002}

# （账户, 候选名, 被替换的核心资产, 换入的资产）——跑之前固定，不得事后增删
CANDIDATES = [
    ("美股账户", "MTUM", ["SPY"], ["MTUM"]),
    ("美股账户", "QUAL", ["SPY"], ["QUAL"]),
    ("美股账户", "VLUE", ["SPY"], ["VLUE"]),
    ("美股账户", "三因子等权", ["SPY"], ["MTUM", "QUAL", "VLUE"]),
    ("A股账户", "512890", ["510880"], ["512890"]),
]
FACTOR_START = {"美股账户": "1963-07-01", "A股账户": None}
# 全部候选都已上市、只用真实 ETF 数据的起点（QUAL 2013-07、512890 2019-01）
RECENT = {"美股账户": "2013-08-01", "A股账户": "2019-02-01"}


def substitute(base: dict, old: list[str], new: list[str], frac: float) -> dict:
    """把 old 资产权重的 frac 比例平分给 new 资产，总权重不变。"""
    out = dict(base)
    moved = sum(base[s] for s in old) * frac
    for s in old:
        out[s] = base[s] * (1 - frac)
    for s in new:
        out[s] = out.get(s, 0.0) + moved / len(new)
    return out


def beats_core(row: dict, core: dict) -> bool:
    """样本内 CAGR 更高，且样本外 CAGR 不低于核心。"""
    return bool(row["is_cagr"] > core["is_cagr"] and row["oos_cagr"] >= core["oos_cagr"])


def excess_sr(sat: pd.Series, bench: pd.Series, start: str | None = None) -> float:
    ex = _excess(sat, bench, start)
    return float(ex.mean() / ex.std(ddof=1))


def _excess(sat, bench, start):
    m = pd.DataFrame({"s": monthly_returns(sat), "b": monthly_returns(bench)}).dropna()
    m = m.loc[start:] if start else m
    return m.s - m.b


def factor_test(sat: pd.Series, bench: pd.Series, n_trials: int, sr_var: float, split: str = SPLIT,
                start: str | None = None, rf: pd.Series | None = None, recent: str | None = None) -> dict:
    """rf：无风险资产价格序列（回归前两边都减）；recent：另算这一天之后（真实 ETF 期）的 t 值。"""
    df = pd.DataFrame({"s": sat, "b": bench}).dropna()
    df = df.loc[start:] if start else df
    ms, mb = monthly_returns(df.s), monthly_returns(df.b)
    mrf = monthly_returns(rf) if rf is not None else None
    r = alpha_t(ms, mb, rf=mrf)
    r["t_recent"] = alpha_t(ms.loc[recent:], mb.loc[recent:], rf=mrf)["t_alpha"] if recent else float("nan")
    r["dsr"] = deflated_sharpe(ms - mb, n_trials, sr_var)
    is_, oos = df.loc[:split], df.loc[split:]
    r["is_excess"] = cagr(is_.s) - cagr(is_.b)
    r["oos_excess"] = cagr(oos.s) - cagr(oos.b)
    r["start"] = f"{df.index[0]:%Y-%m}"
    r["end"] = f"{df.index[-1]:%Y-%m}"
    r["passed"] = bool(r["t_alpha"] >= T_MIN and r["dsr"] >= DSR_MIN)
    return r


def _getters(get_csindex, get_french):
    return {"csindex": get_csindex, "french": lambda code: get_french(*code.split(":"))}


def account_spec(label: str) -> dict:
    a = dict(p3.ACCOUNTS[label])
    if label == "美股账户":
        a["eq"] = ["SPY"] + list(US_SATS)
        a["proxy"] = {s: ("french", c) for s, c in US_SATS.items()}
        a["fee"] = {s: FEES[s] for s in US_SATS}
    else:
        a["eq"] = a["eq"] + ["512890"]
        a["proxy"] = {**a["proxy"], "512890": ("csindex", "H20269")}
        a["fee"] = {"512890": FEES["512890"]}
    return a


def long_series(sym: str, market: str, proxy: tuple, get_price, getters) -> tuple[pd.Series, list[str]]:
    """单个资产的最长历史（代理补齐、扣费），用于因子检验。"""
    a = {"eq": [sym], "bond": [], "gold": [], "market": market, "proxy": {sym: proxy}, "fee": {sym: FEES.get(sym, 0.0)}}
    px, notes = p3.build_prices(a, get_price, None, {}, getters)
    return px[sym], notes


def factor_series(get_price, getters) -> tuple[dict, dict, list[str]]:
    """返回 {候选: 长历史价格}、{账户: 基准长历史}、数据说明。"""
    notes, sats = [], {}
    for s, code in US_SATS.items():
        sats[s], n = long_series(s, "US", ("french", code), get_price, getters)
        notes += n
    rets = pd.DataFrame({s: sats[s].pct_change() for s in US_SATS}).dropna()
    sats["三因子等权"] = (1 + rets.mean(axis=1)).cumprod()
    sats["512890"], n = long_series("512890", "CN", ("csindex", "H20269"), get_price, getters)
    notes += n
    spy, n1 = long_series("SPY", "US", ("french", FF_MKT), get_price, getters)
    hs300, n2 = long_series("510300", "CN", ("csindex", "H00300"), get_price, getters)
    return sats, {"美股账户": spy, "A股账户": hs300}, notes + n1 + n2


def combined_worst(navs: dict, other: dict, w_us: float, label: str) -> tuple[float, pd.Series]:
    us, cn = (navs, other) if label == "美股账户" else (other, navs)
    combs = {m: p3.combine_navs(us[m], cn[m], w_us) for m in ("end", "mid", "start")}
    return min(max_drawdown(c) for c in combs.values()), combs["end"]


def run_implementation(fx, get_price, get_index, getters, w_us, run_id) -> tuple[pd.DataFrame, dict, list[str]]:
    specs, pxs, notes, core_navs, core_rows = {}, {}, [], {}, {}
    for label in CORE:
        a = account_spec(label)
        px, n = p3.build_prices(a, get_price, get_index, fx, getters)
        specs[label], pxs[label] = a, px
        notes += [x for x in n if x.split("：")[0] in ("512890",) + tuple(US_SATS)]
        e, split, signal = CORE[label]
        base = p3._base_weights(p3.ACCOUNTS[label], e, p3.SPLITS[split])
        start = rebalance_dates(px, "end")[12]
        by_mode, cost2, _ = p3.run_trial(px, base, signal, a, fx, start)
        core_navs[label] = (base, start, by_mode)
        core_rows[label] = evaluate(by_mode, cost2, split=SPLIT)
    rows = []
    for label in CORE:
        other = core_navs["A股账户" if label == "美股账户" else "美股账户"][2]
        base0, start, by0 = core_navs[label]
        mdd0, comb0 = combined_worst(by0, other, w_us, label)
        rows.append({"account": label, "candidate": "核心（不替换）", "frac": 0.0, **core_rows[label],
                     "comb_mdd": mdd0, "comb_is": cagr(comb0.loc[:SPLIT]), "comb_oos": cagr(comb0.loc[SPLIT:]),
                     "eligible": True, "beats": None, "passed": None})
        for acc, name, old, new in CANDIDATES:
            if acc != label:
                continue
            for frac in FRACS:
                base = substitute(base0, old, new, frac)
                by_mode, cost2, _ = p3.run_trial(pxs[label], base, CORE[label][2], specs[label], fx, start)
                r = evaluate(by_mode, cost2, split=SPLIT)
                mdd, comb = combined_worst(by_mode, other, w_us, label)
                ok = all(bool(r[g]) for g in p3.ELIGIBLE_GATES)
                beats = beats_core(r, core_rows[label])
                row = {"account": label, "candidate": name, "frac": frac, **r, "comb_mdd": mdd,
                       "comb_is": cagr(comb.loc[:SPLIT]), "comb_oos": cagr(comb.loc[SPLIT:]),
                       "eligible": ok, "beats": beats, "passed": bool(ok and beats and mdd >= MDD_LIMIT),
                       "periods": period_returns(comb)}
                rows.append(row)
                log_trial({"name": f"P4落地｜{label}｜{name}｜替换{int(frac * 100)}%", "phase": "P4", "run_id": run_id,
                           "weights": ";".join(f"{k}={v:.3f}" for k, v in base.items()),
                           **{k: v for k, v in row.items() if k not in ("periods",)}})
    return pd.DataFrame(rows), core_navs, notes


def _pct(x) -> str:
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:.1f}%"


def _ok(x) -> str:
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else ("✓" if x else "✗")


def render(ft: pd.DataFrame, impl: pd.DataFrame, verdict: dict, as_of: date, n_trials: int, data_notes: list[str],
           w_us: float) -> str:
    out = [f"# P4 卫星检验报告（{as_of:%Y-%m-%d}）", "", p3.DISCLAIMER, "",
           "## 结论", ""]
    passed = [k for k, v in verdict.items() if v]
    out += [f"进入 P5 的卫星候选：**{'、'.join(passed) if passed else '无'}**。" +
            ("" if passed else "P5 只用 P3 的核心配置。"), "",
            "| 候选 | 因子证据 | 落地检验（至少一档通过） | 进入 P5 |", "|---|:-:|:-:|:-:|"]
    for name in verdict:
        f_ok = bool(ft.loc[name, "passed"])
        i_ok = bool(impl[impl.candidate == name].passed.fillna(False).any())
        out.append(f"| {name} | {_ok(f_ok)} | {_ok(i_ok)} | {_ok(verdict[name])} |")
    out += ["", "## 方法", "",
            "- 候选在运行前固定：美股 MTUM（动量）、QUAL（质量）、VLUE（价值）及三者等权；A股 512890（红利低波）。"
            f"P4 共 {n_trials} 个试验，全部记入 `research/trials.csv`。",
            f"- **第一层 因子证据**：候选（上市前用代理补齐、扣 ETF 费率）和基准都减去无风险利率（美股 French 一个月国库券，A股中证货币基金指数 H11025）后做月收益回归，"
            "alpha 的 t 值用 Newey-West（3 阶）标准误，t 值对阶数有一定敏感性；"
            f"通缩夏普比率（DSR）按 {n_trials} 次试验折扣。通过条件：t ≥ {T_MIN}（设计文档“接近 3”）且 DSR ≥ {DSR_MIN}。"
            "美股从 1963-07 起，A股从中证红利低波全收益指数起点起。基准：美股 SPY（上市前用 French 全市场，扣 0.0945%），"
            "A股沪深300全收益（扣 510300 费率 0.2%）。",
            "- **第二层 落地检验**：把 P3 核心的股票部分按 25%/50%/100% 换成候选（A股只替换 510880 那一半），信号仍是 10 个月均线转国债，"
            f"人民币口径。通过条件：P3 账户级门槛（样本外、成本×2、调仓日差、去掉最好一年）全过；样本内 CAGR 高于核心且样本外 CAGR 不低于核心；"
            f"和另一个账户的原核心合并后，三种调仓日最差回撤 ≥ {_pct(MDD_LIMIT)}。账户权重：美股 {_pct(w_us)}。",
            "- 进入 P5 = 因子证据通过 **且** 至少一档落地通过。",
            "- “真实 ETF 期 t 值”只用全部候选上市后的数据（美股 2013-08 起，A股 2019-02 起），样本短、只作参考，不参与判定；"
            "它和全期 t 值差得越多，说明证据越依赖早期代理段。", "",
            "## 第一层：因子证据", "",
            "| 候选 | 区间 | 年化 alpha | beta | t 值 | 真实 ETF 期 t 值 | DSR | 样本内年化超额 | 样本外年化超额 | 通过 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|:-:|"]
    for name, r in ft.iterrows():
        out.append(f"| {name} | {r.start} 至 {r.end} | {_pct(r.alpha_ann)} | {r.beta:.2f} | {r.t_alpha:.2f} | {r.t_recent:.2f} | {r.dsr:.2f} | "
                   f"{_pct(r.is_excess)} | {_pct(r.oos_excess)} | {_ok(r.passed)} |")
    out += ["", "## 第二层：落地检验（人民币）", ""]
    for label in CORE:
        sub = impl[impl.account == label]
        out += [f"### {label}", "",
                "| 方案 | 替换比例 | 样本内 | 样本外 | 成本×2 | 单账户最差回撤 | 合并最差回撤 | 合并样本外 | 账户级门槛 | 胜过核心 | 通过 |",
                "|---|---:|---:|---:|---:|---:|---:|---:|:-:|:-:|:-:|"]
        for r in sub.itertuples():
            out.append(f"| {r.candidate} | {_pct(r.frac)} | {_pct(r.is_cagr)} | {_pct(r.oos_cagr)} | {_pct(r.cost2_cagr)} | "
                       f"{_pct(r.mdd_worst)} | {_pct(r.comb_mdd)} | {_pct(r.comb_oos)} | {_ok(r.eligible)} | {_ok(r.beats)} | {_ok(r.passed)} |")
        out.append("")
    good = impl[impl.passed.fillna(False).astype(bool)]
    if len(good):
        out += ["通过落地检验的方案，合并净值分时段收益：", "",
                "| 方案 | " + " | ".join(good.iloc[0].periods) + " |", "|---|" + "---:|" * len(good.iloc[0].periods)]
        for r in good.itertuples():
            out.append(f"| {r.candidate} {_pct(r.frac)} | " + " | ".join(_pct(v) for v in r.periods.values()) + " |")
        out.append("")
    out += ["## 数据说明", ""] + [f"- {n}" for n in dict.fromkeys(data_notes)]
    out += ["", "## 局限", "",
            "- Ken French 组合是“NYSE 中位数以上的大盘股”里按单一指标排前 30% 的市值加权组合，不是 MTUM/QUAL/VLUE 的实际选股规则；"
            "代理段只扣了 ETF 费率，没有扣交易成本。动量代理是**每日重建**的组合（French 原文 constructed daily），零成本下换手极高，代理段收益**明显偏乐观**。",
            "- 三因子等权在因子层按日再平衡、零成本，落地层是月度调仓，两层口径不同。美股基准 2002 年前是 French 全市场（含小盘），候选只含大盘股，alpha 里混有大小盘差异。",
            "- QUAL 的代理用营业利润率（OP），MSCI 质量指数还看 ROE、杠杆、盈利波动，口径不同。",
            "- 落地检验的样本外（2020 年起）全部是真实 ETF 数据；样本内大部分在 ETF 上市前，靠代理。",
            "- 红利低波的代理是全收益指数（分红不扣税、没有跟踪误差），而落地回测里的 510880 全程是真实 ETF 后复权净值；只扣 0.6% 费率未必补足，"
            "样本内对比偏向红利低波。"
            "红利类产品规模膨胀、拥挤度上升（调研报告），历史超额未必延续。",
            "- 因子发表后平均缩水约一半（调研报告引 McLean & Pontiff），历史 alpha 不是预期。",
            "- 回测不代表未来。", ""]
    return "\n".join(out)


def main() -> int:
    import warnings
    warnings.filterwarnings("ignore")
    from quant.data.update import get_csindex, get_french, get_index, get_price

    fx = {"AUDUSD": get_price("AUDUSD", "FX", "fx"), "AUDCNY": get_price("AUDCNY", "FX", "fx")}
    getters = _getters(get_csindex, get_french)
    run_id = new_run_id()
    n_trials = len(CANDIDATES) * (len(FRACS) + 1)

    sats, benches, notes = factor_series(get_price, getters)
    acc = {name: a for a, name, _, _ in CANDIDATES}
    srs = [excess_sr(sats[n], benches[acc[n]], FACTOR_START[acc[n]]) for n in acc]
    sr_var = float(np.var(srs, ddof=1))
    # 无风险利率：美股 French RF（一个月国库券），A股中证货币基金指数 H11025
    rfs = {"美股账户": get_french("F-F_Research_Data_Factors_daily", "RF"), "A股账户": get_csindex("H11025")}
    ft = {}
    for name, label in acc.items():
        ft[name] = factor_test(sats[name], benches[label], n_trials, sr_var, start=FACTOR_START[label],
                               rf=rfs[label], recent=RECENT[label])
        log_trial({"name": f"P4因子｜{name}", "phase": "P4", "run_id": run_id, **ft[name]})
    ft = pd.DataFrame(ft).T

    w_us = p3.current_w_us(fx)
    impl, _, impl_notes = run_implementation(fx, get_price, get_index, getters, w_us, run_id)
    verdict = {n: bool(ft.loc[n, "passed"]) and bool(impl[impl.candidate == n].passed.fillna(False).any()) for n in acc}

    as_of = date.today()
    path = Path("reports") / f"P4-卫星-{as_of}.md"
    path.write_text(render(ft, impl, verdict, as_of, n_trials, notes + impl_notes, w_us))
    print(f"已生成：{path}")
    print("进入 P5：", [k for k, v in verdict.items() if v])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
