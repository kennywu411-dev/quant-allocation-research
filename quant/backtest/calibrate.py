"""P2 校准报告：python -m quant.backtest.calibrate"""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant.backtest import costs
from quant.backtest.crosscheck import run_bt
from quant.backtest.engine import run_backtest
from quant.backtest.strategies import buy_and_hold, sma_timing
from quant.fx import to_aud
from quant.metrics import cagr, max_drawdown

SECTION_TITLES = ["一、买入持有复现", "二、与 bt 交叉核对", "三、开关影响", "四、参照公开结论（Faber 均线择时）"]
DISCLAIMER = "> 声明：本报告不是投资建议，回测结果不代表未来收益。本报告只检验回测引擎是否可信，不推荐任何策略。"


def summary(nav: pd.Series) -> dict:
    r = nav.pct_change().dropna()
    vol = float(r.std() * np.sqrt(252))
    return {"CAGR": cagr(nav), "最大回撤": max_drawdown(nav), "年化波动": vol,
            "夏普": float(r.mean() * 252 / vol) if vol > 0 else float("nan")}


def _fmt(v, col: str = "") -> str:
    if ("成本" in col or "被挡" in col) and isinstance(v, (float, np.floating)):
        return f"{v:,.0f}"
    if isinstance(v, (float, np.floating)):
        return "—" if np.isnan(v) else (f"{v:.2f}" if abs(v) > 5 else f"{v * 100:.2f}%")
    return str(v)


def _table(df: pd.DataFrame) -> list[str]:
    out = ["| | " + " | ".join(map(str, df.columns)) + " |", "|---" * (len(df.columns) + 1) + "|"]
    for i, row in df.iterrows():
        out.append(f"| {i} | " + " | ".join(_fmt(v, c) for c, v in row.items()) + " |")
    return out


def render(sections: dict[str, pd.DataFrame], as_of: date, notes: dict[str, str] | None = None) -> str:
    out = [f"# P2 回测引擎校准报告（{as_of:%Y-%m-%d}）", "", DISCLAIMER, ""]
    for t in SECTION_TITLES:
        out += [f"## {t}", ""]
        if notes and t in notes:
            out += [notes[t], ""]
        out += _table(sections[t]) + [""]
    return "\n".join(out)


def rules_note(blocked: int) -> str:
    if blocked == 0:
        return ("本样本中 A股涨跌停、停牌规则一次都没触发（510300 最接近封板的几天都在容差之外），"
                "所以“A股规则”一行和上一行相同；规则逻辑由单元测试验证，不是由这份数据验证的。")
    return f"本样本中 A股规则共挡住 {blocked} 次订单，订单顺延到下一个交易日。"


def _from(nav: pd.Series, weights: pd.DataFrame) -> pd.Series:
    first_exec = nav.index[nav.index > weights.index[0]][0]
    return nav.loc[first_exec:]


def main() -> int:
    from quant.data.update import get_price

    fx = {"AUDUSD": get_price("AUDUSD", "FX", "fx"), "AUDCNY": get_price("AUDCNY", "FX", "fx")}
    us = pd.DataFrame({"SPY": get_price("SPY", "US", "etf"), "IEF": get_price("IEF", "US", "etf")}).dropna()
    cn = pd.DataFrame({"510300": get_price("510300", "CN", "etf"), "511010": get_price("511010", "CN", "etf")})
    cn = cn.loc[cn["510300"].first_valid_index():]

    # 一、买入持有复现
    s1 = {}
    for name, px, sym in (("SPY", us, "SPY"), ("510300", cn, "510300")):
        one = px[[sym]].dropna()
        w = buy_and_hold(one, {sym: 1.0})
        nav = _from(run_backtest(one, w, {sym: costs.zero()}, fractional=True).nav, w)
        raw = one[sym].loc[nav.index[0]:]
        s1[name] = {"引擎 CAGR": cagr(nav), "原始序列 CAGR": cagr(raw), "差（百分点）": (cagr(nav) - cagr(raw)) * 100}
    s1 = pd.DataFrame(s1).T

    # 二、与 bt 交叉核对
    s2 = {}
    cases = {
        "SPY 均线择时（下方持 IEF）": (us, sma_timing(us, "SPY", 10, "IEF")),
        "510300 均线择时（下方持 511010）": (cn.dropna(), sma_timing(cn.dropna(), "510300", 10, "511010")),
    }
    for name, (px, w) in cases.items():
        ours = _from(run_backtest(px, w, {c: costs.zero() for c in px}, fractional=True).nav, w)
        theirs = run_bt(px, w).loc[ours.index[0]:]
        s2[name] = {"本引擎 CAGR": cagr(ours), "bt CAGR": cagr(theirs),
                    "CAGR 差（百分点）": (cagr(ours) - cagr(theirs)) * 100,
                    "本引擎最大回撤": max_drawdown(ours), "bt 最大回撤": max_drawdown(theirs),
                    "回撤差（百分点）": (max_drawdown(ours) - max_drawdown(theirs)) * 100}
    s2 = pd.DataFrame(s2).T

    # 三、开关影响（美股按 1 万美元、A股按 10 万元起始资金）
    s3 = {}
    cn_blocked = 0
    us_w = cases["SPY 均线择时（下方持 IEF）"][1]
    cn_w = sma_timing(cn, "510300", 10, "511010")
    variants = [
        ("SPY 择时", us, us_w, {"SPY": costs.us_etf(), "IEF": costs.us_etf()}, 10_000.0, "USD", False),
        ("510300 择时", cn, cn_w, {"510300": costs.cn_etf(), "511010": costs.cn_etf()}, 100_000.0, "CNY", True),
    ]
    for label, px, w, cm, init, ccy, is_cn in variants:
        zero = {c: costs.zero() for c in px}
        runs = {
            "零成本、零碎股": run_backtest(px, w, zero, init, fractional=True),
            "加成本、零碎股": run_backtest(px, w, cm, init, fractional=True),
            "加成本、整手": run_backtest(px, w, cm, init),
        }
        if is_cn:
            runs["加成本、整手、A股规则"] = run_backtest(px, w, cm, init, cn_rules=True)
            cn_blocked = runs["加成本、整手、A股规则"].blocked
        last = list(runs)[-1]
        for k, r in runs.items():
            nav = _from(r.nav, w)
            s3[f"{label}｜{k}"] = {"CAGR": cagr(nav), "最大回撤": max_drawdown(nav), "年换手（单边）": r.turnover,
                                   "成本合计": r.total_cost, "被挡订单": r.blocked}
        nav_aud = _from(to_aud(runs[last].nav, ccy, fx), w)
        s3[f"{label}｜{last}｜澳元计价"] = {"CAGR": cagr(nav_aud), "最大回撤": max_drawdown(nav_aud),
                                         "年换手（单边）": runs[last].turnover, "成本合计": runs[last].total_cost,
                                         "被挡订单": runs[last].blocked}
    s3 = pd.DataFrame(s3).T

    # 四、参照 Faber：均线择时应显著降低最大回撤，牛市可能跑输
    bh_w = buy_and_hold(us[["SPY"]], {"SPY": 1.0})
    bh = _from(run_backtest(us[["SPY"]], bh_w, {"SPY": costs.us_etf()}, 10_000.0).nav, bh_w)
    tm = _from(run_backtest(us, us_w, {"SPY": costs.us_etf(), "IEF": costs.us_etf()}, 10_000.0).nav, us_w)
    tm = tm.loc[bh.index[0]:] if tm.index[0] < bh.index[0] else tm
    bh = bh.loc[tm.index[0]:]

    def _yr(n, y):
        s = n.loc[f"{y}-01-01":f"{y}-12-31"]
        return s.iloc[-1] / s.iloc[0] - 1

    s4 = pd.DataFrame({
        "SPY 买入持有": {"CAGR": cagr(bh), "最大回撤": max_drawdown(bh), "2008 年收益": _yr(bh, 2008), "2022 年收益": _yr(bh, 2022)},
        "SPY 10 月均线择时": {"CAGR": cagr(tm), "最大回撤": max_drawdown(tm), "2008 年收益": _yr(tm, 2008), "2022 年收益": _yr(tm, 2022)},
    }).T

    notes = {
        SECTION_TITLES[0]: "零成本、零碎股，从第一笔成交日起算。差值应 < 0.01 个百分点。",
        SECTION_TITLES[1]: "两边同样零成本、零碎股、调仓日次日收盘成交。CAGR 差应 < 0.05 个百分点，回撤差 < 0.1 个百分点。",
        SECTION_TITLES[2]: ("美股按 1 万美元、A股按 10 万元起始，成本取值见设计文档第 4 节；“澳元计价”行体现汇率影响。"
                            "510300 这一组从 510300 上市（2012 年）起算，511010 上市前跌破均线时持现金，"
                            "所以起点和第二节（两只都上市后才开始）不同，数字不能直接对比。" + rules_note(cn_blocked)),
        SECTION_TITLES[3]: (f"数据从 {tm.index[0]:%Y-%m-%d} 开始，不能和 Faber 论文（1901 年起）逐项对数字，只检验方向："
                            "择时应明显降低最大回撤、减少 2008 年亏损，代价可能是长期收益略低。"),
    }
    as_of = date.today()
    md = render(dict(zip(SECTION_TITLES, [s1, s2, s3, s4])), as_of, notes)
    path = Path("reports") / f"P2-回测校准-{as_of}.md"
    path.write_text(md)
    print(f"已生成：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
