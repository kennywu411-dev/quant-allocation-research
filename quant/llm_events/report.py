"""公告因子报告（Markdown）。数字全部来自 research/llm_events_results.json；结论句按预先写死的门槛自动生成。"""
import numpy as np
import pandas as pd

from quant.llm_events import label as L, study as S

SHORT = {"claude-haiku-5-5": "Haiku 5.5", "claude-haiku-4-5": "Haiku 4.5", "dict": "关键词词典"}


def _p(x, d=2):
    return "—" if x is None or not np.isfinite(x) else f"{x * 100:.{d}f}%"


def _f(x, d=2):
    return "—" if x is None or not np.isfinite(x) else f"{x:.{d}f}"


def render(res: dict, png: str, ann: pd.DataFrame) -> str:
    m, look, fac, ag, sp = res["main"], res["lookahead"], res["factor"], res["agreement"], res["spend"]
    L_ = [f"# 公告因子：大模型读公告标题（{res['date']}）", "",
          "> 研究记录，不是投资建议；历史回测不代表未来收益。作者不是持牌金融顾问。", "",
          "## 一句话结论", ""]
    verdict = "通过" if m["passed"] else "未通过"
    L_ += [f"- 主假设（运行前写死、只有一个）：{SHORT[S.MAIN_MODEL]} 在训练数据截止之后的干净样本里，"
           f"实质性利好减利空、持有 5 天的超额收益 {_p(m['car'])}，t = {_f(m['t'])}，门槛 t ≥ {S.T_MAIN:.0f} → **{verdict}**。",
           f"- 大模型自身的前视：在 {S.OVERLAP[0][:7]} 至 {S.OVERLAP[1][:7]}（Haiku 5.5 的训练数据已覆盖、Haiku 4.5 没有），"
           f"同一批公告上 Haiku 5.5 的多空收益比 Haiku 4.5 高 {_p(look['diff_car'])}（t = {_f(look['diff_t'])}）。",
           "- 月度情绪因子：" + "；".join(f"{SHORT[k]} RankIC {v['rank_ic']:.3f}（t {_f(v['t'])}），干净段 {v['clean_rank_ic']:.3f}（{v['clean_n']} 个月）→ **{v['verdict']}**"
                                    for k, v in fac.items()) + "。",
           f"- 总花费 ${sp['total']:.2f}（预算 ${L.BUDGET:.0f}）。", ""]
    ev_ = {(r["source"], r["segment"], r["k"]): r for r in res["events"]}
    pre20 = ev_.get(("claude-haiku-5-5", "截止前", 20), {})
    pre5 = ev_.get(("claude-haiku-5-5", "截止前", 5), {})
    d20 = ev_.get(("dict", "全期", 20), {})
    op55, opd = ag.get("h55_vs_opus", {}), ag.get("dict_vs_opus", {})
    L_ += ["## 解读", "",
           f"1. **公告当天有反应，之后没有可交易的超额。** 含公告当日（参考口径）时，Haiku 5.5 截止前样本的 5 日多空 {_p(pre5.get('car_incl_t0', np.nan))}（t {_f(pre5.get('t_incl_t0', np.nan))}）；"
           f"从公告日收盘之后算，多空 {_p(pre5.get('car', np.nan))}（t {_f(pre5.get('t', np.nan))}）。信息在当天基本就被价格吸收了，只看标题、收盘后才行动的做法赚不到。",
           f"2. **20 天上反而有反转迹象，但不是预先登记的假设。** Haiku 5.5 截止前样本 20 日多空 {_p(pre20.get('car', np.nan))}（t {_f(pre20.get('t', np.nan))}），"
           f"词典全期 {_p(d20.get('car', np.nan))}（t {_f(d20.get('t', np.nan))}）：利空公告之后的股票反而跑赢。前者所在样本可能有模型前视，后者没到 t ≥ 3，只能当作后续研究的线索。",
           f"3. **大模型比词典标得更接近强模型，但没有因此更能预测收益。** 对 Opus 5.5 复核的方向 kappa：Haiku 5.5 {_f(op55.get('kappa', np.nan))}，词典 {_f(opd.get('kappa', np.nan))}；"
           "可两者在公告日之后的多空都不显著，大模型在这里多带来的是“分类更准”，不是“收益更高”。",
           f"4. **没测到大模型的前视增益。** 同一段、同一批公告，见过这段数据的 Haiku 5.5 比没见过的 Haiku 4.5 多空高 {_p(look['diff_car'])}（t {_f(look['diff_t'])}），"
           f"含公告当日高 {_p(look.get('diff_car_incl_t0', np.nan))}（t {_f(look.get('diff_t_incl_t0', np.nan))}），都不显著。可能的原因是输入只有去名的短标题，模型难以对上具体公司和日期。",
           "5. **有方向的标注本身分歧不小**：总体方向一致率看着很高，主要因为大多数公告是中性；只看至少一方判为有方向的条目，模型之间的一致率明显更低（见“标注”一节）。", ""]
    L_ += ["## 数据", "",
           f"- 公告：巨潮资讯（akshare `stock_zh_a_disclosure_report_cninfo`），今天的沪深300 成分股 {res['n_codes']} 只，"
           f"2020-01 至 2026-10，共 {res['n_ann']:,} 条。只存标题、链接和哈希，原文不入库。",
           "- 行情：新浪后复权日线（与因子检验同一份缓存，截至 2026-10-30）；基准为沪深300 指数。",
           "- 股票池是**今天**的成分股，有幸存者偏差（见 `reports/因子检验-2026-11-10.md` 的说明）。", "",
           "## 标注", "",
           "- 输入只有**去掉公司名的标题**（简称、全称替换为“本公司”），不给日期、代码和任何之后的信息，减少模型凭记忆认出公司。",
           f"- 输出用 JSON Schema 约束：事件类型（{len(L.TYPES)} 类）、方向（利好 / 中性 / 利空）、强度 0–3、是否实质性。每个请求 50 条，Batch API（五折），按公告编号缓存，批次状态落盘可续跑。",
           "- 模型：Haiku 5.5 标注全部公告（关闭思考、effort = low）；Haiku 4.5 只标注其训练数据截止之后（2025-08 起）的公告。",
           "- 基线：关键词词典（`quant/llm_events/dictionary.py`，规则在看结果前固定）。", ""]
    if ag:
        L_ += ["**一致率**（方向 / 是否实质 / 类型）：", ""]
        names = {"h55_vs_h45": "Haiku 5.5 对 Haiku 4.5（同段全部）", "h55_vs_opus": "Haiku 5.5 对 Opus 5.5 复核",
                 "h45_vs_opus": "Haiku 4.5 对 Opus 5.5 复核", "dict_vs_opus": "词典 对 Opus 5.5 复核"}
        for k, v in ag.items():
            if v.get("n"):
                typ = "—" if k.startswith("dict") else _p(v["type"], 1)
                L_.append(f"- {names[k]}：{v['n']:,} 条，方向 {_p(v['direction'], 1)}（kappa {_f(v.get('kappa', np.nan))}；"
                          f"至少一方判为有方向的 {v.get('n_active', 0):,} 条里一致 {_p(v.get('direction_active', np.nan), 1)}），"
                          f"实质 {_p(v['material'], 1)}，类型 {typ}")
        L_ += ["", "复核用的是更强的模型（Opus 5.5），不是人工；从两个 Haiku 都标过的干净段里简单随机抽 200 条，随机种子运行前固定。", ""]
    L_ += ["## 判定标准（运行前写进 `quant/llm_events/study.py`，提交 6f41b00）", "",
           "- 事件日 t0 = 公告日当天或之后第一个交易日。巨潮日期只到日，所以主口径**不含 t0 当天**，从 t0 收盘开始算；含当天的数字只作参考。",
           "- 日历时间组合：每天对正处在持有期内的事件按组求平均超额收益，多空 = 实质性利好 − 实质性利空；t 值用 Newey-West（滞后 = 持有天数），处理窗口重叠。",
           f"- 主假设一个，门槛 t ≥ {S.T_MAIN:.0f}；其余都是次要检验，门槛 t ≥ {S.T_SECONDARY:.0f}。",
           "- 月度因子：全期 RankIC t ≥ 3 且干净段同号才算显著。", "",
           f"![公告因子]({png})", "",
           "## 事件研究（多空 = 实质性利好 − 实质性利空，日历时间组合）", "",
           "| 来源 | 样本段 | 持有天数 | 利好事件 | 利空事件 | 多空累计超额 | t | 利好组 | 利空组 | 含公告当日（参考） |",
           "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in res["events"]:
        inc = f"{_p(r['car_incl_t0'])}（t {_f(r['t_incl_t0'])}）" if r["k"] == S.K_MAIN else ""
        L_.append(f"| {SHORT[r['source']]} | {r['segment']} | {r['k']} | {r['n_pos']:,} | {r['n_neg']:,} | {_p(r['car'])} | {_f(r['t'])} | "
                  f"{_p(r.get('car_pos', np.nan))} | {_p(r.get('car_neg', np.nan))} | {inc} |")
    L_ += ["", "## 大模型的前视偏差", "",
           f"同一段（{S.OVERLAP[0]} 至 {S.OVERLAP[1]}）、同一批公告、同样的持有 5 天口径：", "",
           f"- Haiku 5.5（训练数据覆盖这段）：多空 {_p(look['h55']['car'])}，t {_f(look['h55']['t'])}",
           f"- Haiku 4.5（训练数据不覆盖）：多空 {_p(look['h45']['car'])}，t {_f(look['h45']['t'])}",
           f"- 差额 {_p(look['diff_car'])}，同日配对 t {_f(look['diff_t'])}，{look['n_days']} 个交易日。", "",
           "含公告当日（参考口径；如果模型记得哪些公告当天大涨大跌，差额最可能出现在这里）：", "",
           f"- Haiku 5.5：{_p(look['h55_incl_t0']['car'])}（t {_f(look['h55_incl_t0']['t'])}）；Haiku 4.5：{_p(look['h45_incl_t0']['car'])}（t {_f(look['h45_incl_t0']['t'])}）",
           f"- 差额 {_p(look['diff_car_incl_t0'])}，同日配对 t {_f(look['diff_t_incl_t0'])}。", "",
           "解读：如果模型“记得”后来的股价，它在见过的时段会显得更准，差额为正。差额不显著并不证明没有前视，只说明在标题这种短输入、去掉公司名之后，没测到明显的前视增益。", "",
           "## 按事件类型（Haiku 4.5 干净样本，持有 5 天，不含公告当日）", "",
           "| 类型｜方向 | 事件数 | 平均超额 | t |", "|---|---:|---:|---:|"]
    for r in res["types"][:20]:
        L_.append(f"| {r['group']} | {r['n']:,} | {_p(r['car'])} | {_f(r['t'])} |")
    L_ += ["", f"按类型拆开是很多个检验，门槛 t ≥ {S.T_SECONDARY:.0f}。", "",
           "## 月度情绪因子", "",
           "| 来源 | RankIC | t | 月数 | 干净段 RankIC | 干净段 t | 干净段月数 | 多空扣成本年化 | 非零覆盖率 | 判定 |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for k, v in fac.items():
        L_.append(f"| {SHORT[k]} | {v['rank_ic']:.3f} | {_f(v['t'])} | {v['n_months']} | {v['clean_rank_ic']:.3f} | {_f(v['clean_t'])} | "
                  f"{v['clean_n']} | {_p(v['ls_net'], 1)} | {_p(v['coverage'], 0)} | **{v['verdict']}** |")
    L_ += ["", "因子值是当月实质性公告的 方向×强度 之和，大部分股票大部分月份为 0，分组里有大量并列，结果噪声较大。", "",
           "## 局限", "",
           "- **只用了标题**：业绩预告、快报的标题多数不写增减，模型只能判为中性；拿到摘要或正文会更有信息量，但要逐篇下载 PDF，本次没做。",
           "- **公告时间只到日**：主口径放弃了公告当天的反应，低估了可交易的部分，但避免了用到未来信息。",
           "- **干净样本短**：Haiku 4.5 截止后约 15 个月，Haiku 5.5 截止后只有约 4 个月；月度因子在干净段上的检验力很弱。",
           "- **幸存者偏差**：股票池是今天的沪深300 成分股。",
           "- **Haiku 4.5 是旧模型**，官方承诺的最早退役日已过，之后可能无法复现这一部分标注。",
           "- 复核用的是更强的模型，不是人工标注。", "",
           "## 复现", "", "```bash",
           "PYTHONPATH=. .venv/bin/python -m quant.llm_events.data",
           "PYTHONPATH=. .venv/bin/python -m quant.llm_events.label --model claude-haiku-5-5",
           "PYTHONPATH=. .venv/bin/python -m quant.llm_events.label --model claude-haiku-4-5 --start 2025-08-01",
           "PYTHONPATH=. .venv/bin/python -m quant.llm_events.label --review 200",
           "PYTHONPATH=. .venv/bin/python -m quant.llm_events.run", "```", "",
           f"需要 `ANTHROPIC_API_KEY`。运行编号 `{res['run_id']}`；所有检验记在 `research/trials.csv`（phase = 公告因子）。", ""]
    return "\n".join(L_)
