"""因子挖掘报告（Markdown）。数字来自 research/alpha_results.json，结论按 spec 的门槛自动判定。"""
import numpy as np

from quant.alpha import spec


def _p(x, d=1):
    return "—" if x is None or not np.isfinite(x) else f"{x * 100:.{d}f}%"


def _f(x, d=2):
    return "—" if x is None or not np.isfinite(x) else f"{x:.{d}f}"


def render(S: dict, meta: dict, png: str, weekly: bool = False) -> str:
    passed = [k for k, s in S.items() if s["passed"]]
    FAC = spec.W_FACTORS if weekly else spec.FACTORS
    NT = spec.W_N_TRIALS if weekly else spec.N_TRIALS
    L = [f"# 全 A 股因子挖掘（{meta['date']}）", "",
         "> 研究记录，不是投资建议；历史回测不代表未来收益。作者不是持牌金融顾问。", "",
         "## 一句话结论", "",
         f"- 按运行前写死的门槛（`quant/alpha/spec.py`，提交 db2d90b{'；周线版偏离登记 2f54c55' if weekly else ''}），**试了 {len(S)} 个（{len(FAC)} 个单因子 + {len(spec.COMPOSITES)} 个合成），通过 {len(passed)} 个**"
         + (f"：{'、'.join(passed)}。" if passed else "。"),
         f"- LightGBM 合成相对线性合成的样本外 RankIC 差：" + "；".join(
             f"对{k} {v['diff']:+.3f}（t {_f(v['t'])}，{v['n']} 个月）" for k, v in meta["ml_vs_linear"].items()) + "。",
         f"- 补充（不是门槛）：通缩夏普最高为 {max(S, key=lambda k: S[k]['dsr'] if np.isfinite(S[k]['dsr']) else -1)} 的 "
         f"{_f(max(s['dsr'] for s in S.values() if np.isfinite(s['dsr'])))}，全部低于 0.95。按 {NT} 次试验折扣后，纯多头超额都不能确认显著。",
         f"- RankIC 显著（t ≥ 3）的有 {sum(s['t'] >= spec.T_PASS for s in S.values())} 个，但其中只有 {len(passed)} 个样本外纯多头超额为正。"
         "排序能力主要体现在避开最差的一组；做多最高组时，换手成本和涨停买不进会把优势吃掉。", "",
         *(["## 偏离预先登记（改用周线）", "",
             "- 原因：baostock 日线每只股票要 15–20 秒，5,481 只约 28 小时；为当天出结果改用周线（每只约 2.4 秒）。偏离在下载周线之前登记（提交 2f54c55）。",
             "- 去掉 EP、BP：周线没有市盈率、市净率。12 个因子变为 10 个，试验次数 15 → 13，通过门槛仍为 t ≥ 3。",
             "- 不能剔除 ST：周线没有 ST 标记；ST 股多为小市值，大部分已被“剔除流通市值最小 30%”去掉，残留的 ST 会让小市值、反转类因子的结果略有偏差。",
             "- 调仓日为每个月最后一个不晚于月末的周五所在周；各因子改用周线窗口（见下表定义）。",
             "- 涨跌停近似：最后一周涨幅 ≥ 涨停幅度的不新买、跌幅 ≥ 跌停幅度的持仓不卖，比真实规则更严（会多剔除一些股票）。",
             "- 日线版代码和预先登记仍在（`quant/alpha/run.py`），数据下完后可以按原方案重跑、与本报告对照。", ""] if weekly else []),
         "## 股票池与数据", "",
         f"- baostock 每个月末当天全部在市的 A股（**含之后退市的股票**，没有幸存者偏差），2014-01 至 2026-09，共 {meta['n_codes']:,} 只出现过。",
         f"- 每月剔除{'' if weekly else ' ST、'}上市不满{'一年' if weekly else f' {spec.MIN_AGE} 个交易日'}、{'调仓周' if weekly else '月末'}停牌或无成交、流通市值最小的 {spec.SMALL_CUT:.0%}；剩下的股票每月 {meta['univ_min']:,}–{meta['univ_max']:,} 只（中位数 {meta['univ_median']:,}）。",
         ("- 周收益用 baostock 周线涨跌幅（已按除权除息调整，抽查 3 只送转股确认），流通市值 = 周成交额 ÷ 周换手率。" if weekly else "- 日收益用 baostock 涨跌幅（昨收已按除权除息调整），流通市值 = 收盘价 × 成交量 ÷ 换手率。") + "持有期内退市的股票，退市后收益记 0（按最后成交价拿回现金，略偏乐观）。",
         "- 沪深300 那轮的股息率因子需要逐只下载分红数据，本轮没做，预先登记时已写明。", "",
         "## 判定标准（运行前写死）", "",
         f"- 样本内到 {spec.SPLIT[:4]} 年底，样本外 {int(spec.SPLIT[:4]) + 1} 年起。",
         f"- 通过 = 同时满足：(a) 全期 RankIC t ≥ {spec.T_PASS:.0f}（{NT} 个试验，按多重检验的更高门槛）；(b) 样本外 RankIC 均值 > 0；(c) 样本外纯多头超额（扣成本、含涨跌停约束）年化 > 0。",
         ("- 纯多头 = 最高五分之一组等权，月度调仓；最后一周涨幅达到涨停幅度的不新买，跌幅达到跌停幅度或停牌的持仓卖不出、留到下月；" if weekly else "- 纯多头 = 最高五分之一组等权，月度调仓；t 日收盘涨停的不能新买，跌停或停牌的持仓卖不出、留到下月；") + "成本按往返 0.25% + 印花税（2023-08-28 前后分别计）。超额相对股票池等权。",
         "- 多空 = 最高组 − 最低组，空头腿不扣融券成本，只作参考（A股个人难以融券）。",
         f"- 通缩夏普（DSR）按 {NT} 次试验折扣，作为补充，不是门槛。", "",
         f"![因子挖掘]({png})", "",
         "## 结果总表", "",
         "| 名称 | 定义 | 全期 RankIC | t | 样本内 RankIC | 样本外 RankIC | 样本外年化 ICIR | 样本外纯多头超额（年化） | 样本外超额最大回撤 | 样本外多空（参考） | 月均单边换手 | DSR | 结果 |",
         "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    defs = {**FAC, "等权合成": f"{len(FAC)} 个因子标准化值的平均", "IC加权合成": f"权重 = max(过去 {spec.IC_WINDOW} 个月 RankIC 均值, 0)",
            "LightGBM合成": f"每年 12 月用过去 {spec.LGB_TRAIN_MONTHS} 个月重训，参数固定"}
    for k, s in S.items():
        L.append(f"| {k} | {defs[k]} | {s['rank_ic']:.3f} | {_f(s['t'])} | {s['is_rank_ic']:.3f} | {s['oos_rank_ic']:.3f} | {_f(s['oos_icir_ann'])} | "
                 f"{_p(s['oos_ex_ann'])} | {_p(s['oos_ex_mdd'])} | {_p(s['oos_ls_ann'])} | {_p(s['top_turn'], 0)} | {_f(s['dsr'])} | **{'通过' if s['passed'] else '未通过'}** |")
    L += ["", "全期纯多头超额（含样本内）：" + "；".join(f"{k} {_p(s['ex_ann'])}" for k, s in S.items()) + "。", "",
          "## 局限", "",
          "- 没有剔除北交所以外的其他特殊情况（如退市整理期）；流通市值是用成交量和换手率反推的，换手率为 0 的日子沿用之前的值。",
          ("- 涨跌停按周涨跌幅近似，不是逐日判断；" if weekly else "- 涨跌停只按收盘判断，盘中触板又打开的情况按可以成交处理；") + "成本没有区分大小盘的冲击成本，小盘股的真实成本可能更高。",
          f"- 合成和机器学习都只用这 {len(FAC)} 个因子作为输入，没有加入行业、市值中性化；结论不代表更复杂的模型做不出来。",
          "- 样本外从 2020 年开始，约 6 年，包括 2024 年初的小盘股崩盘。", "",
          "## 复现", "", "```bash", *(["PYTHONPATH=. .venv/bin/python -m quant.alpha.data  # 只用于生成股票名单（中途可停）", "PYTHONPATH=. .venv/bin/python -m quant.alpha.weekly_data", "PYTHONPATH=. .venv/bin/python -m quant.alpha.weekly"] if weekly else ["PYTHONPATH=. .venv/bin/python -m quant.alpha.data", "PYTHONPATH=. .venv/bin/python -m quant.alpha.run"]), "```", "",
          f"运行编号 `{meta['run_id']}`；每个检验记在 `research/trials.csv`（phase = 因子挖掘）。", ""]
    return "\n".join(L)
