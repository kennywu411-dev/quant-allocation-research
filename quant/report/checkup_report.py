"""把持仓体检结果渲染成中文 Markdown 报告。只描述风险数字，不给买卖建议。"""
from datetime import date

import pandas as pd

from quant.metrics import cagr, current_drawdown, max_drawdown

DISCLAIMER = "> 声明：本报告不是投资建议，回测和历史数据不代表未来收益。作者不是持牌金融顾问。"
LIMIT = -0.20

SECTIONS = ["一、持仓概况", "二、历史最大回撤", "三、最差 5 次回撤", "四、压力区间",
            "五、相关性", "六、风险贡献", "七、单只持仓回撤", "八、数据说明"]


def _pct(x: float) -> str:
    return "—" if pd.isna(x) else f"{x * 100:.1f}%"


def _d(x) -> str:
    return "未恢复" if pd.isna(x) else pd.Timestamp(x).strftime("%Y-%m-%d")


def _proxied(notes: list[str]) -> str:
    """代理说明形如“代码：……”，取出代码。"""
    return "、".join(n.split("：")[0] for n in notes) or "部分标的"


def render(h, nav, values_aud, risk_contrib, corr, stress, worst, proxy_notes, as_of: date,
           asset_dd: pd.DataFrame | None = None, sources: dict | None = None,
           nav_ref: pd.Series | None = None, estimates: list[str] | None = None,
           data_info: pd.DataFrame | None = None, rc_real: pd.Series | None = None,
           real_since: str | None = None) -> str:
    total = values_aud.sum()
    mdd, cdd = max_drawdown(nav), current_drawdown(nav)
    out = [f"# 持仓体检报告（{as_of:%Y-%m-%d}）", "", DISCLAIMER, ""]

    out += [f"## {SECTIONS[0]}", "", f"总市值约 **A${total:,.0f}**（按最新价格和汇率换算成澳元）。", "",
            "| 持仓 | 澳元市值 | 占比 |", "|---|---:|---:|"]
    for k, v in values_aud.sort_values(ascending=False).items():
        out.append(f"| {k} | {v:,.0f} | {_pct(v / total)} |")
    if estimates:
        out += ["", "**⚠️ 以下数字是估算值，结论对它们很敏感，请按 App 实际数字修改 `config/holdings.csv` 后重跑：**", ""]
        out += [f"- {e}" for e in estimates]

    out += ["", f"## {SECTIONS[1]}", "",
            f"把**今天的持仓比例**（含现金，现金也计汇率波动）放回 {nav.index[0]:%Y-%m-%d} 以来的历史，"
            "每天再平衡到今天的比例，按澳元计：", "",
            "| 指标 | 数值 |", "|---|---:|",
            f"| 历史最大回撤 | **{_pct(mdd)}** |",
            f"| 你设定的上限 | {_pct(LIMIT)} |",
            f"| 当前距最高点 | {_pct(cdd)} |",
            f"| 年化收益（回放期，有后视偏差） | {_pct(cagr(nav))} |"]
    if nav_ref is not None:
        out.append(f"| 参考：按现在股数不变回放的最大回撤 | {_pct(max_drawdown(nav_ref))} |")
    out += ["",
            "说明：年化收益有**后视偏差**：这些股票是今天回头看才持有的，过去涨得好不代表未来，这个数字不能当作预期收益。"
            "回撤数字更有参考意义，它说明这种持仓结构在历史上会跌多深。",
            "",
            "股数不变的回放里，越早的年份股价越低、现金占比越高，回撤会被稀释，所以只作参考。" if nav_ref is not None else "",
            "",
            f"历史最大回撤是上限的 **{mdd / LIMIT:.1f} 倍**。" if mdd < LIMIT else "历史最大回撤在上限以内。", ""]

    out += [f"## {SECTIONS[2]}", "", "| 高点 | 最低点 | 恢复 | 跌幅 |", "|---|---|---|---:|"]
    for r in worst.itertuples():
        out.append(f"| {_d(r.peak)} | {_d(r.trough)} | {_d(r.recovery)} | {_pct(r.depth)} |")

    out += ["", f"## {SECTIONS[3]}", "", "现在这个组合放回历史上几段典型下跌期（— 表示回放期还没覆盖到）：", "",
            "| 事件 | 区间 | 区间收益 | 区间最大回撤 |", "|---|---|---:|---:|"]
    for name, r in stress.iterrows():
        out.append(f"| {name} | {r['区间']} | {_pct(r['收益'])} | {_pct(r['最大回撤'])} |")

    out += ["", f"## {SECTIONS[4]}", "",
            "周收益相关系数（1 = 同涨同跌；用周收益是因为 A股和美股收盘时间不同，日收益会低估相关性）。"
            + (f"{_proxied(proxy_notes)} 上市前用的是代理数据，对应那一行可信度低。" if proxy_notes else ""), "",
            "| | " + " | ".join(corr.columns) + " |", "|---" * (len(corr.columns) + 1) + "|"]
    for i, row in corr.iterrows():
        out.append(f"| {i} | " + " | ".join(f"{v:.2f}" for v in row) + " |")

    real_col = rc_real is not None
    out += ["", f"## {SECTIONS[5]}", "", "每项持仓贡献了组合波动的多少（加总 100%，现金的风险来自汇率）：", "",
            "| 持仓 | 资金占比 | 风险贡献（全历史） |" + (f" 风险贡献（仅 {real_since} 以后真实数据） |" if real_col else ""),
            "|---|---:|---:|" + ("---:|" if real_col else "")]
    for k, v in risk_contrib.sort_values(ascending=False).items():
        extra = f" {_pct(rc_real.get(k, float('nan')))} |" if real_col else ""
        out.append(f"| {k} | {_pct(values_aud.get(k, 0) / total)} | {_pct(v)} |" + extra)
    if real_col:
        out += ["", f"全历史那一列里 {_proxied(proxy_notes)} 上市前用的是代理数据；右边一列只用真实数据，但样本很短，两列都只能作参考。"]

    out += ["", f"## {SECTIONS[6]}", ""]
    if asset_dd is not None:
        out += ["| 持仓 | 数据起点 | 历史最大回撤 | 当前距最高点 |", "|---|---|---:|---:|"]
        for k, r in asset_dd.iterrows():
            out.append(f"| {k} | {r['start']} | {_pct(r['max_dd'])} | {_pct(r['cur_dd'])} |")
    out.append("")

    out += [f"## {SECTIONS[7]}", ""]
    out += [f"- {n}" for n in proxy_notes]
    if sources:
        out.append("- 数据来源：" + "，".join(f"{k}={v}" for k, v in sources.items()))
    if data_info is not None:
        out += ["", "| 序列 | 最后日期 | 来源 | 抓取时间 | 是否旧缓存 |", "|---|---|---|---|---|"]
        for k, r in data_info.iterrows():
            out.append(f"| {k} | {r['最后日期']} | {r['来源']} | {r['抓取时间']} | {'⚠️ 旧缓存（更新失败）' if r['旧缓存'] else '否'} |")
        out.append("")
    out += ["- 价格均为复权价（分红、拆股已处理），再按当日或之前最近一天的汇率换算成澳元，不使用未来数据。",
            "- 回放是把今天的持仓放回历史，不代表你过去实际的收益。", ""]
    return "\n".join(out)
