# 先验证再下注：A股美股量化策略证据地图

> 调研日期：2026-10-30。综合 5 份子调研笔记写成（趋势与资产配置、美股因子、A股因子与规则、框架与研究流程、数据与券商接口）。
> **可信度标注**：【高】= 同行评审论文、监管机构或交易所原文、框架源码；【中】= 指数公司、机构白皮书（可能有商业立场）、主流财经媒体转述；【低】= 论坛、博客、客户经理问答、比价站。标"推断"的是本报告的推理，不是来源原话。
> **声明**：本报告不是投资建议。回测和历史数据不代表未来收益。作者不是持牌顾问。

对一个从零起步、目标是"长期总体盈利"的个人投资者，证据最扎实的几条路线都偏"慢"：美股的价值、动量、质量/低风险因子，A股的 EP 价值、短期反转、低异常换手和红利低波，再加上跨资产的趋势过滤和风险预算配置。它们有几十年数据支持，但发表之后的收益平均缩水约一半，最差阶段都要承受 20%–60% 的回撤，或者连续 3 年以上跑输大盘 ([CXO Advisory 综述 McLean & Pontiff](https://www.cxoadvisory.com/big-ideas/effects-of-market-adaptation)【高】；[Alpha Architect](https://alphaarchitect.com/do-interest-rates-explain-values-underperformance/)【中】)。A股和美股的因子结构明显不同：**A股没有月度动量，1 个月反转最强，最小 30% 市值的股票被壳价值污染**，所以美式 12-1 动量不能直接照搬 ([Liu, Stambaugh & Yuan 2019](https://faculty.wharton.upenn.edu/wp-content/uploads/2018/03/Size-and-Value-in-China.pdf)【高】)。A股的散户还要面对只能做多、T+1、涨跌停、融券基本停摆（规模约占流通市值 0.05%）这些约束，很多因子收益集中在拿不到的空头腿上 ([证监会](https://www.csrc.gov.cn/csrc/c100028/c7493852/content.shtml)【高】)。工具上，Qlib 适合做 A股研究主干，但它**默认不限涨跌停、冲击成本为 0**，不手动设置就会高估收益 ([qlib exchange.py](https://github.com/microsoft/qlib/blob/main/qlib/backtest/exchange.py)【高】)。执行端，moomoo AU 的 OpenAPI 官方文档写明可以实盘交易美股股票和 ETF ([moomoo AU 帮助中心](https://www.moomoo.com/au/support/topic3_436)【中，表格列映射需实测】)；银河 QMT 的开通门槛只有互相矛盾的二手说法（从"无门槛"到 10 万、50 万元不等），必须你亲自向营业部书面确认。本报告不替你选定最终策略，只给出有证据的候选、它们各自的坑，以及一条按优先级排好的回测路径。

## 美股因子大多能复制，但要按论文数字的四到五成来预期

美股是证据最厚的市场，学界的争论焦点已经从"因子存不存在"转到"还剩多少"。McLean & Pontiff 研究了 97 个已发表的预测变量，多空月均毛收益在样本内是 0.58%，发表后降到 0.26%，**发表后平均缩水约 58%**，其中约 32 个百分点被归因于投资者按论文交易；衰减最快出现在发表后第 3–4 年，而且只用价格数据、样本内 t 值越高的因子衰减越大 ([CXO Advisory](https://www.cxoadvisory.com/big-ideas/effects-of-market-adaptation)【高，二手综述】)。后续研究估计，衰减会随时间累积：样本结束后 5 年约 -40%，10 年约 -50%，发表偏差只解释其中约 12% ([arXiv 2105.01380](https://arxiv.org/pdf/2105.01380)【中，预印本】)。Hou、Xue、Zhang 复制了 447 个异象，改用 NYSE 分位点和市值加权、压低微盘股的影响之后，**64% 在 5% 水平上不显著，门槛提到 t≥3 时 85% 不显著** ([NBER w23394](https://www.nber.org/papers/w23394.pdf)【高】)。反方是 Jensen、Kelly、Pedersen（JF 2023），他们用贝叶斯框架检验 93 个国家的 153 个因子，结论是多数可以复制，13 个主题里有 10 个复制率超过 75%，例外是季节性、杠杆和规模 ([NBER w28432](https://www.nber.org/papers/w28432)【高，作者有 AQR 背景】)。两边其实并不矛盾：经典的大类因子是真的，但边缘异象多数是噪声，而且真因子的幅度也比论文小。

规模是最弱的一个。AQR 的 Alquist 等人发现，即使在最初发现的那段时期，规模效应也不如价值和动量强，大量发表之后没有显著正溢价 ([AQR PDF](https://www.Aqr.Com/-/media/AQR/Documents/Whitepapers/Fact-Fiction-and-the-Size-Effect.pdf?sc_lang=en)【中，作者是 AQR】)。引用 DFA 的数据，1982–2017 年美股规模溢价的几何年化是 **0.0%** ([Advisor Perspectives](https://www.advisorperspectives.com/articles/2018/07/12/the-size-effect-is-not-dead)【中】)。质量和低贝塔高度重叠：独立检验发现，贝塔异象集中在低质量股票里，加入 QMJ 之后 BAB 的 alpha 就消失了 ([Adelaide](https://digital.library.adelaide.edu.au/items/ea6b10cd-d450-4b70-b2f1-c66fdfc824f4/full)【中】)。

最差阶段要按实际情况去准备。动量的尾部风险出现在熊市之后的急反弹：2009 年 3–5 月，过去的输家上涨约 156%–163%，赢家只涨约 8% ([Daniel & Moskowitz, NBER w20439](https://www.nber.org/system/files/working_papers/w20439/w20439.pdf)【高】)，多空动量约 3 个月回撤 **-73%**（这是二手数字，而且是多空组合） ([ETF.com](https://www.etf.com/sections/index-investor-corner/swedroe-downside-momentum)【中】)。价值从 2017 年 1 月到 2020 年 3 月回撤约 42%，从 2007 年算起约 51%，用单变量价值排序则是 47% 和 59%，是有记录以来最长、最深的一次寒冬 ([Alpha Architect](https://alphaarchitect.com/do-interest-rates-explain-values-underperformance/)【中】)。2026 年三季度，S&P 500 的价值因子指数 +0.19%，动量 -2.42%，质量 -5.48%，低波 -6.26%，同期指数 +2.25% ([CME Group](https://www.cmegroup.com/articles/2026/factors-2026-q3-review-q4-outlook-with-factor-futures.html)【中，来自搜索摘要】)。

只做多仍然能保留相当一部分溢价。Israel & Moskowitz 发现，多头腿贡献了几乎全部规模溢价、约 60% 的价值溢价和约一半的动量收益 ([AQR/JFE 2013](https://www.aqr.com/Insights/Research/Journal-Article/The-Role-of-Shorting-Firm-Size-and-Time-on-Market-Anomalies)【高】)。成本方面，Novy-Marx & Velikov 的结论是：**月换手低于约 50% 的异象，多数在扣成本后仍有显著净收益**，最有效的单一降本手段是"买入门槛高于持有门槛"（buy/hold spread） ([NBER w20721](https://nber.org/papers/w20721)【高】)。传统的 1 个月反转扣成本后基本为零，只有在大盘股里做、或者用剔除因子暴露后的残差反转，才可能存活 ([CEPR DP15857](https://repec.cepr.org/repec/cpr/ceprdp/DP15857.pdf)【高】)。因子 ETF 的实盘可以作为参照：PortfoliosLab 统计的成立以来年化，MTUM 15.19%、QUAL 13.59%、USMV 11.89%、VLUE 13.41%，SPY 10.80% ([PortfoliosLab](https://portfolioslab.com/symbol/MTUM)【低，各基金起始日不同】)；2020 年 3 月 MTUM、QUAL 回撤约 -34%，VLUE 约 -39%，和大盘差不多 ([TotalRealReturns](https://totalrealreturns.com/n/MTUM,QUAL,VLUE)【低】)。也就是说，只做多的因子组合主要是**换了一种风格的股票 beta，不能替你规避熊市**。

择时叠加的作用是买保险，不是提高收益。有人在 SPY 上独立复现 Faber 的 10 个月均线：33 年里往返交易 23 次，最大回撤不到 SPY 的一半，但胜率的置信区间包含 50%，最近 3 年年化 12.9%，而 SPY 是 22.3% ([empiricalab](https://empiricalab.substack.com/p/faber-10-month-average)【低】)。另外，结果对调仓日很敏感 ([Newfound](https://blog.thinknewfound.com/2013/08/the-luck-of-the-rebalance-timing/)【中】)。

### 美股候选策略对比表

下表的"预期扣费收益区间"和"实现难度"是**本报告的推断**：做法是把论文溢价乘以 0.4–0.5 的衰减系数，再扣掉换手成本，并参照 ETF 实盘数据。这些数字只是你回测时的"合理先验"，不是承诺。

| 候选 | 证据强度 | 预期扣费收益（推断） | 历史最大回撤（有来源者） | 换手 | 实现难度 | 主要来源 |
|---|---|---|---|---|---|---|
| 价值（多指标、市值加权、剔除微盘） | 高（复制率高） | 只做多：大盘 + 0–2%/年超额，可能连续 3–5 年跑输 | HML 多空 -42%～-59%（2007/2017–2020） | 低（季/半年调仓） | 中 | [Alpha Architect](https://alphaarchitect.com/do-interest-rates-explain-values-underperformance/)、[NBER w28432](https://www.nber.org/papers/w28432) |
| 动量（12-1，大中盘） | 高 | 只做多：大盘 + 0–2%/年；换手高，应税账户税负重 | 多空约 -73%（2009，二手）；MTUM 2020 年约 -34% | 高 | 中 | [NBER w20439](https://www.nber.org/system/files/working_papers/w20439/w20439.pdf)、[TotalRealReturns](https://totalrealreturns.com/n/MTUM,QUAL,VLUE) |
| 质量/盈利（QMJ 类） | 高（美国 + 24 国） | 大盘 + 0–1.5%/年，下跌时防守较好 | QUAL 2020 年约 -34% | 低 | 中（需 PIT 财务数据） | [AQR QMJ](https://www.aqr.com/Insights/Research/Working-Paper/Quality-Minus-Junk?aqrPDF=1) |
| 低贝塔/低波 | 中高（和质量重叠） | 收益接近大盘，波动更低；2026Q3 表现最差 | 2026Q3 季度 -6.26% | 低 | 低 | [CME](https://www.cmegroup.com/articles/2026/factors-2026-q3-review-q4-outlook-with-factor-futures.html)、[Adelaide](https://digital.library.adelaide.edu.au/items/ea6b10cd-d450-4b70-b2f1-c66fdfc824f4/full) |
| 规模（单独做） | 低 | 约 0（1982–2017 几何年化 0.0%） | AVUV 2020 年 -49%（小盘价值） | 低 | 低 | [Advisor Perspectives](https://www.advisorperspectives.com/articles/2018/07/12/the-size-effect-is-not-dead)、[PortfoliosLab](https://portfolioslab.com/tools/stock-comparison/AVUV/IWN) |
| 价值 + 动量 + 质量组合 | 高（价值和动量负相关） | 大盘 + 1–2%/年（推断），回撤比单因子平滑 | 无统一来源 | 中 | 中 | [SSRN 3229719](https://papers.ssrn.com/abstract=3229719) |
| 短期反转（1 个月） | 中（只在大盘、残差版有效） | 散户扣价差后接近 0 | 无来源 | 极高 | 高 | [CEPR DP15857](https://repec.cepr.org/repec/cpr/ceprdp/DP15857.pdf) |
| 10 个月均线 / 双动量择时 | 中低（多为样本内或博客复现） | 长期略低于买入持有，回撤减半 | 熊市回撤约为 SPY 的一半 | 很低 | 低 | [empiricalab](https://empiricalab.substack.com/p/faber-10-month-average)、[reblnc](https://reblnc.com/insights/dual-momentum) |

## A股的因子结构和美股相反，红利低波是回撤最可控的那一类

A股的基准文献是 Liu、Stambaugh、Yuan（JFE 2019，样本 2000–2016）。在剔除最小 30% 的"壳"股票之后，SMB 月均 1.03%，VMG（基于 EP 的价值因子）月均 1.11%，t 值分别约为 3.32 和 4.16，而市场因子的 t 值只有 1.16 ([LSY](https://faculty.wharton.upenn.edu/wp-content/uploads/2018/03/Size-and-Value-in-China.pdf)【高】)。在 A股，**价值要用 EP，不用 BM**：四个估值比率同时放进回归时，EP 的 t 值是 4.14，BM 只有 1.22 ([同上](https://faculty.wharton.upenn.edu/wp-content/uploads/2018/03/Size-and-Value-in-China.pdf)【高】)。最关键的差异在动量上：过去 1、3、6、12 个月乃至 5 年的收益都**负向**预测未来收益，按 1 个月收益排序的"输家减赢家"组合，CAPM alpha 是年化 18%（t=2.96）；按 1 年收益排序就降到 6%，而且不显著 ([同上](https://faculty.wharton.upenn.edu/wp-content/uploads/2018/03/Size-and-Value-in-China.pdf)【高】)。清华五道口的工作论文从 T+1 带来的隔夜和日内收益结构来解释月频动量为什么消失 ([清华五道口 PDF](https://www.pbcsf.tsinghua.edu.cn/__local/E/AD/3B/F24944A5ADC8089108B27D57291_3994F5E6_CBB03.pdf?e=.pdf)【中，工作论文】)。另一个显著因子是异常换手率（过去 20 日平均换手 ÷ 过去 250 日平均换手）：做多低异常换手、做空高异常换手的 PMO 因子年化约 12%，LSY 把这归因于散户持有 88% 的自由流通股，加上做空成本极高 ([LSY](https://faculty.wharton.upenn.edu/wp-content/uploads/2018/03/Size-and-Value-in-China.pdf)【高】)。投资、应计和非流动性这三类在美股显著的异象，在 A股并不显著。

这些证据有两个硬伤。第一，样本截止到 2016 年，之后的注册制、退市新规和量化资金扩张都在改变结构，样本外表现只能自己验证。第二，散户只能做多，而反转和高换手这类异象的收益有不少来自空头腿，实际能拿到的会明显打折（推断）。

小盘因子在 A股"没有死，但会周期性地剧烈崩盘"。2024 年 1 月 2 日到 2 月 5 日，中证2000 区间下跌 **32.84%**，是成立以来最大的区间跌幅，其中 2 月 5 日单日跌 9.49% ([复旦发展研究院](https://fddi.fudan.edu.cn/2b/23/c21253a666403/page.htm)【中】；[第一财经](https://www.yicai.com/news/101985905.html)【中】)。机制是几件事相互放大：雪球产品敲入、股指期货贴水扩大、DMA 和中性策略平仓。不少百亿量化指增产品单周跌 10%–17% ([华尔街见闻](https://wallstreetcn.com/articles/3709236)【中】)。紧接着，2024 年 4 月新"国九条"收紧退市标准，主板财务退市的营收门槛从 1 亿元提高到 3 亿元，ST 板块在 4 月 15 日到 6 月 7 日之间下跌 32%，壳价值被系统性削弱 ([中证网](https://www.cs.com.cn/xwzx/hg/202404/t20240418_6403005.html)【中】；[同花顺/证券时报](https://news.10jqka.com.cn/20240418/c657005942.shtml)【中】)。到了 2025 年，私募指增产品平均回报 45.08%，平均超额 16.75%，中证1000 指增平均超额 17.49% ([证券时报/同花顺](https://news.10jqka.com.cn/20260121/c674173909.shtml)【中】)，又证明这个风险敞口很快就能修复。要注意，这是机构在全 A 市场做多因子并用期货对冲的结果，散户只做多、做 20–50 只股票，很难复制。

红利低波是 A股回撤最可控的候选。根据界面新闻转述的 Wind/财通证券数据，2015 年 7 月到 2026 年 6 月，中证红利低波全收益指数年化约 **13.75%**，最大回撤 **22.1%**（2018 年底），同期沪深300 最大回撤 46.8% ([界面新闻](https://m.jiemian.com/article/14715469.html)【中，口径未独立核实，应以中证指数公司数据为准】)。2025 年末，红利类策略产品规模约 2445 亿元 ([第一财经](https://www.yicai.com/news/102434541.html)【中】)，拥挤度在上升。2025 年中证红利约 -1.39% ([理杏仁](https://www.lixinger.com/equity/fund/detail/jj/022927/22927/monthly-change)【低】)，说明它也会有平淡的年份。

ETF 轮动和指数择时在 A股**缺乏可引用的权威证据**。网上流传的"年化 453%"一类 ETF 双池轮动，属于典型的过拟合营销 ([CSDN](https://gitcode.csdn.net/69eb21d254b52172bc6fc38b.html)【低，不应采信】)。结合"个股无动量、强反转"这一点推断，短窗口的指数趋势容易被反转吃掉；MA120、MA250 这类长窗口趋势过滤，更适合当作规避 2015、2018 年这种系统性熊市的风控工具，而不是 alpha 来源。这需要你自己回测验证。

### A股候选策略对比表

收益区间同样是推断：以 LSY 的因子收益为上限，乘以只做多和发表后衰减的折扣，再扣掉估算成本。

| 候选 | 证据强度 | 预期扣费收益（推断） | 历史最大回撤（有来源者） | 换手 | 实现难度 | 主要来源 |
|---|---|---|---|---|---|---|
| 红利低波（指数/ETF 或自建） | 中（指数长期数据，非学术） | 接近指数长期水平，但规模膨胀后预期下调；年化 13.75% 是历史值，不是预期 | -22.1%（2018，全收益） | 很低 | 低 | [界面新闻](https://m.jiemian.com/article/14715469.html) |
| EP 价值（剔除最小 30% 市值） | 高（LSY，t≈4） | 宽基 + 0–4%/年超额（只做多、2016 年后需验证） | 无一手来源 | 低-中 | 中（需 PIT 财务数据） | [LSY](https://faculty.wharton.upenn.edu/wp-content/uploads/2018/03/Size-and-Value-in-China.pdf) |
| 低异常换手 / 低换手 | 高（PMO 年化约 12%，多空） | 多头腿打折后 + 0–4%/年（推断） | 无一手来源 | 中 | 中 | [LSY](https://faculty.wharton.upenn.edu/wp-content/uploads/2018/03/Size-and-Value-in-China.pdf) |
| 1 个月反转 | 高（年化 alpha 18%，多空毛收益） | 扣 T+1、涨跌停和成本后不确定，可能接近 0 | 无来源，存在跌停无法卖出的尾部风险 | 高（月度约 100%） | 中高 | [LSY](https://faculty.wharton.upenn.edu/wp-content/uploads/2018/03/Size-and-Value-in-China.pdf) |
| 小市值轮动 | 中（长期有效，但周期性崩盘） | 波动极大，年度区间很宽 | 中证2000 -32.8%（约 1 个月）；ST 板块 -32% | 高 | 低（但风控难） | [复旦](https://fddi.fudan.edu.cn/2b/23/c21253a666403/page.htm)、[中证网](https://www.cs.com.cn/xwzx/hg/202404/t20240418_6403005.html) |
| 多因子组合（EP + 低换手 + 低波 + 盈利 + 反转） | 中高（机构指增 2025 超额约 17%，但含对冲和规模优势） | 宽基 + 2–6%/年（推断，散户只做多会更低） | 量化指增 2024 年初单周 -10%～-17% | 中-高 | 高 | [同花顺](https://news.10jqka.com.cn/20260121/c674173909.shtml)、[华尔街见闻](https://wallstreetcn.com/articles/3709236) |
| 12-1 动量（美式） | 低（A股不成立） | 不建议作为主信号 | — | 高 | 中 | [LSY](https://faculty.wharton.upenn.edu/wp-content/uploads/2018/03/Size-and-Value-in-China.pdf) |
| 宽基/行业 ETF 轮动、均线择时 | 低（无权威证据） | 未知，需自建样本外检验 | 无可靠来源 | 低-中 | 低 | [CSDN（反例）](https://gitcode.csdn.net/69eb21d254b52172bc6fc38b.html) |

## 趋势跟踪和资产配置是"保险型"收益，2022 年改写了风险平价的假设

时间序列动量（趋势跟踪）有最长的学术证据。Moskowitz、Ooi、Pedersen 发现，在 58 个期货和远期合约上，12 个月时间序列动量**对每一个合约**都是正收益 ([SSRN](https://papers.ssrn.com/abstract=2089463)【高】)。AQR 把回测延伸到 1880 年、67 个市场，结论是在随后约 110 年里持续盈利 ([AQR](https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing)【中，作者是 AQR 员工】)。但实盘和回测之间落差很大。2010–2019 年 SG Trend Index 年均只有 **1.8%**，同期 60/40 是 7.5% ([Institutional Investor](https://www.institutionalinvestor.com/article/b20qbzzskkwdz7/aqr-it-s-not-too-late-to-bet-on-managed-futures)【中】)。它在危机年份表现突出：2008 年 +20.9%（MSCI ACWI -42.2%），2022 年 +27.4%（ACWI -18.4%）；但 2024 年 5 月到 2025 年 5 月回撤 **-20.4%**，2000 年以来超过 10% 的回撤一共 16 次，大约每 18–24 个月一次 ([Cambridge Associates](https://www.cambridgeassociates.com/insight/does-trend-followings-recent-struggle-signal-that-the-strategy-is-structurally-broken/)【中】)。一份从业者报告给出的长期 CAGR 是 4.03% ([Top Traders Unplugged](https://www.toptradersunplugged.com/trend-following-performance-report-october-2025/)【低】)。对个人来说，比较合理的预期是"夏普 0.3–0.5、单次回撤 15–25%"（推断）。

波动率目标在样本内看起来很漂亮：Moreira-Muir 报告夏普提升约 50%–100% ([NBER w22208](https://www.nber.org/papers/22208)【高】)。但 Cederburg 等人用 103 个策略做真实的样本外检验，只有 8 个显著改善；原文的 alpha 依赖全样本前视来匹配波动率 ([Lehigh PDF](https://www.lehigh.edu/~xuy219/research/COWY.pdf)【高】)。所以波动率目标更适合当风险上限工具，不适合当 alpha 来源。

风险平价的核心假设是股债负相关，2022 年这个假设失效了。美股和债券的相关系数从 20 年均值 -0.12 跳到 +0.51 ([ThinkAdvisor](https://thinkadvisor.com/2022/10/17/is-the-6040-portfolio-dead-or-just-resting)【中】)，美股 60/40 约 -17.5% ([Advisor Perspectives](https://www.advisorperspectives.com/articles/2023/05/25/long-live-60-40-portfolio)【中】)，用约 1.2 倍杠杆持有长债的风险平价 ETF RPAR 从高点回撤约 32% ([Bloomberg](https://www.bloomberg.com/news/articles/2022-09-28/-perfect-storm-for-risk-parity-has-etf-posting-record-32-drop)【中】)。加入黄金、商品和趋势跟踪是补这个短板的常见做法（推断）。Faber 的 GTAA 在扩展到 2025 年 3 月的样本里，CAGR 6.05%、夏普 0.68、最大回撤 11.7%，但仅仅改变调仓日就会显著改变结果 ([Concretum](https://concretumgroup.com/global-tactical-asset-allocation/)【低-中，从业者】)。另外，1994–2016 年的战术配置共同基金整体是负 alpha ([USM](https://aquila.usm.edu/fac_pubs/20187)【高】)。

跨市场分散对同时持有 A股和美股的投资者有实际价值。截至 2021 年的 10 年月度数据，沪深300 与标普500 的相关系数是 0.44 ([Mackenzie](https://www2.mackenzieinvestments.com/content/dam/mackenzie/en/insights/mi-why-china-investor-page-en.pdf)【中】)。S&P 的测算显示，77% 美股加 23% A股的组合，风险调整收益（0.75）高于单独持有标普500（0.67）或沪深300（0.47） ([S&P Global](https://www.spglobal.com/en/research-insights/articles/the-potential-value-of-u-s-equity-allocation-to-chinese-investors)【中，指数商】)。但在 2020 年 4 月，两者的 120 日相关性升到 2002 年以来最高 ([QuantConnect](https://www.quantconnect.com/blog/?p=3368)【中】)，说明在全球危机里这种分散会失效。如果最终计价货币是澳元，CNY 和 USD 资产都有汇率暴露，相关性和回撤应该换成澳元口径重新计算（推断，没有找到相关研究）。

| 候选（ETF 可落地） | 证据强度 | 预期扣费收益（推断/来源） | 历史最大回撤 | 换手 | 实现难度 | 来源 |
|---|---|---|---|---|---|---|
| 趋势跟踪（多资产 10 个月均线 / 12 个月动量） | 高（学术）/ 中（实盘） | 实盘 CTA 长期约 4%/年 | SG Trend -20.4%（2024–25） | 低 | 低-中 | [Cambridge Associates](https://www.cambridgeassociates.com/insight/does-trend-followings-recent-struggle-signal-that-the-strategy-is-structurally-broken/) |
| Faber GTAA | 中（发表后延续了低回撤） | CAGR 约 6%，夏普 0.68 | -11.7% | 很低 | 低 | [Concretum](https://concretumgroup.com/global-tactical-asset-allocation/) |
| 风险平价（股、债、金、商品） | 中（2022 年暴露缺陷） | 取决于杠杆和资产池，无可靠预期 | RPAR 约 -32%～-35% | 低 | 中 | [Bloomberg](https://www.bloomberg.com/news/articles/2022-09-28/-perfect-storm-for-risk-parity-has-etf-posting-record-32-drop) |
| 60/40 基准 | 高（长期） | 长期基准 | 2022 年约 -17% | 很低 | 很低 | [Advisor Perspectives](https://www.advisorperspectives.com/articles/2023/05/25/long-live-60-40-portfolio) |
| 波动率目标叠加 | 中（样本外多数无效） | 不提高收益，主要平滑波动 | — | 中 | 低 | [Cederburg et al.](https://www.lehigh.edu/~xuy219/research/COWY.pdf) |

## A股规则会改变回测结果：T+1、涨跌停、只做多和程序化报告

印花税在 2023 年 8 月 28 日减半征收，这是 2008 年以来的首次下调 ([新华网](https://www.news.cn/2023-08/28/c_1212260850.htm)【中，转述官方公告】)。目前通行的理解是卖方单边 0.05%、ETF 免征，但子调研没有拿到条文原文，需要核实。融券基本已经停摆：2024 年 1 月 29 日起全面暂停限售股出借，7 月 11 日起暂停转融券，融券保证金比例提到 100%（私募 120%），到 2024 年 6 月底融券规模只占流通市值约 0.05% ([证监会](https://www.csrc.gov.cn/csrc/c100028/c7493852/content.shtml)【高】)。这意味着散户的 A股量化**只能做多**，LSY 的多空因子收益只能拿到多头腿。涨跌停规则是一般 ±10%、ST ±5%、部分品种 ±20%、新股首日不设限 ([FSMOne](https://support.fsmone.com.my/hc/en-us/sections/9935583077391-6-Trading-in-different-markets)【低，券商说明】)；创业板、科创板 20%，北交所 30%，以及 100 股一手的细节，需要你用交易所规则原文核实。回测里必须做到三点：当天买入的不能当天卖出（T+1），涨停时不能买入、跌停时不能卖出，停牌期间不能成交。短期反转策略恰好最常买到跌停股，遇到跌停也无法止损，所以对这些规则最敏感（推断）。按卖出印花税 0.05% 加双边佣金估算，月度换手 100% 的策略年化成本约 1.5%–2%（推断，需按你的实际佣金重算）。

程序化交易监管的影响主要在合规手续，不在策略本身。证监会的《证券市场程序化交易管理规定（试行）》于 2024 年 10 月 8 日施行 ([证监会](https://www.csrc.gov.cn/csrc/c100028/c7480577/content.shtml)【高】)，沪深北交易所的实施细则于 2025 年 7 月 7 日施行，核心是"先报告、后交易"。高频的认定标准是单账户每秒申报加撤单 ≥300 笔，或单日 ≥20000 笔；异常交易监控分四类：瞬时申报速率异常、频繁瞬时撤单、拉抬打压、短时间大额成交 ([上交所](https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20250403_10776805.shtml)【高】)。新华网引述的分析认为，中小个人投资者极少触发这些指标 ([新华网](https://www.news.cn/money/20250407/3142c6f5fd1d4b1ebd9eb91910befc5e/c.html)【中】)。推断下来，日频或分钟级的低频策略远低于高频线，但只要是程序自动下单，就要通过券商履行报告义务；如果你自己看信号、手工下单，合规负担最小。这一点要以细则对"程序化交易"的定义为准。

## 防过拟合的门槛比策略选择更重要

成熟机构和学界在验证纪律上有比较一致的共识。Harvey、Liu、Zhu 认为，在数百个因子被提出之后，新因子的 t 值门槛应该提高到 **3.0** ([NBER w20592](https://www.nber.org/papers/w20592)【高】)。Bailey 等人提出用组合对称交叉验证（CSCV）估计回测过拟合概率（PBO），并指出传统的 hold-out 方法在投资回测里"不可靠" ([Risk.net](https://www.risk.net/journal-of-computational-finance/2471206/the-probability-of-backtest-overfitting)【高】)；他们还指出，只要试过的变体相对数据量偏多就构成过拟合，而且只需要试相对少量的配置就能得到很高的回测表现 ([Bailey et al.](https://www.davidhbailey.com/dhbpapers/overfitting.pdf)【高】)。通缩夏普比率（DSR）同时修正"从多个策略里挑最好的那个"造成的选择偏差，以及收益分布的非正态，需要输入试验次数 ([SSRN 2460551](https://papers.ssrn.com/abstract=2460551)【高】)。用机器学习时，交叉验证要做 purge（删除和测试集标签区间重叠的训练样本）和 embargo（在测试集之后留一段缓冲） ([Wikipedia](https://en.wikipedia.org/wiki/Purged_cross-validation)【中】)；"embargo 不少于持有期 2 倍"只是从业者的经验法则 ([tradingstrategy.ai](https://tradingstrategy.ai/docs/learn/backtesting.html)【低】)。用 LLM 做情绪因子要格外小心：Glasserman & Lin 发现，样本内的优势大部分来自模型对未来事件的"记忆"，也就是前视偏差 ([arXiv 2309.17322](https://arxiv.org/abs/2309.17322)【中】)；Lopez-Lira 的最新版本也承认，随着 LLM 普及，这类策略的收益在下降 ([arXiv 2304.07619v6](https://arxiv.org/pdf/2304.07619v6)【中】)。

由此推断，你的系统需要一张**试验登记表**：每换一个参数或因子就记一行。没有它，DSR 和 PBO 都算不出来。候选策略晋级的门槛可以设成：t > 3 或 DSR 显著；PBO 较低；成本翻倍后仍然盈利；样本外收益打 5–7 折后仍能覆盖成本；分年度、分市值档看都没有只靠单一时段撑起来；不同调仓日的结果稳定。

### 推荐系统架构与工具选型

下面是本报告的推断方案，各个组件都有来源，但整体组合不是哪一个来源直接推荐的。框架现状来自 2026 年 10 月 30 日的 GitHub API 和 PyPI 数据 ([Qlib](https://github.com/microsoft/qlib)、[vn.py](https://github.com/vnpy/vnpy)、[backtrader](https://github.com/mementum/backtrader)【高】)。

| 层 | 推荐 | 理由与坑 |
|---|---|---|
| 数据层 | 本地 Parquet + DuckDB；A股：BaoStock 打底、Tushare 2000 积分档补财务、AKShare 补零散；美股：原型用 yfinance，严肃回测用 Sharadar 或 EODHD（含退市股） | Tushare 日线需 120 分，财务和复权需 2000 分 ([Tushare](https://tushare.pro/document/1?doc_id=108)【高】)；yfinance 反复出现 429 限流 ([issue #2422](https://github.com/ranaroussi/yfinance/issues/2422)【中】)；Sharadar 保留退市公司 ([Pickuma](https://pickuma.com/for-dev/financial-modeling-prep-vs-sharadar-fundamental-data-api/)【低】)。必须保存已退市股票、复权因子、停牌标记、涨跌停价，财务数据按公告日对齐 |
| 因子/研究层（A股） | Qlib（MIT，约 4.98 万星，2026-10 仍活跃） | 有 Alpha158 和完整 ML 流水线。**坑**：`limit_threshold` 默认 None（不限涨跌停），`impact_cost` 默认 0（不计滑点）；`open_cost=0.0015`、`close_cost=0.0025`、`min_cost=5` 是偏保守的费率，要按实际佣金改；官方数据集已暂停，Yahoo 数据"可能不完美" ([exchange.py](https://github.com/microsoft/qlib/blob/main/qlib/backtest/exchange.py)、[README](https://github.com/microsoft/qlib/blob/main/README.md)【高】)。T+1 需要自己确认或实现 |
| 研究层（美股 / 资产配置） | vectorbt 开源版做快速扫描，bt 做资产配置，zipline-reloaded 或 Lean 做事件驱动复核 | vectorbt 是单人维护、主力在付费 PRO 版，许可证是"Fair Code" ([vectorbt](https://github.com/polakowo/vectorbt)【高】)；参数网格扫描本身就是多次试验，必须计入 DSR |
| 不建议 | backtrader（最后一次 PyPI 发布在 2023-04）；RQAlpha 仅限非商业使用 | ([PyPI backtrader](https://pypi.org/project/backtrader/)、[RQAlpha](https://github.com/ricequant/rqalpha)【高】) |
| 风险报告层 | 自建：夏普、PSR/DSR、CPCV 下的 PBO、t 值、成本 ×2 敏感性、分年分市值档、调仓日敏感性 | 见上文的验证文献 |
| 执行层（A股） | 银河 miniQMT（xtquant）或 PTrade；vn.py 4.x 可选（内置 vnpy.alpha，网关是 XTP/TORA，**不是银河**） | miniQMT 需要常开的 Windows 机器，macOS 不能原生运行（背景知识，未取到来源）；vn.py 支持 Windows 11+ 和 Ubuntu 22.04+ ([vnpy](https://github.com/vnpy/vnpy)【高】) |
| 执行层（美股） | moomoo OpenAPI（OpenD 网关支持 macOS/Linux/Windows，SDK 支持 Python 等），先用模拟盘 | AU 账户可以实盘交易美股股票和 ETF，不支持美股期权和期货 ([moomoo AU](https://www.moomoo.com/au/support/topic3_436)、[OpenAPI 文档](https://openapi.moomoo.com/moomoo-api-doc/en/intro/intro.html)【中】)；总资产低于 1 万港币时只有 100 个订阅和 100 个历史 K 线额度，不能用来拉全市场历史数据 ([权限页](https://openapi.moomoo.com/moomoo-api-doc/en/intro/authority.html)【高】) |
| 环境 | Python 3.12 | 能同时满足 nautilus（>=3.12）、vectorbt 和 zipline（>=3.11）以及 Qlib（classifiers 列到 3.12）的要求（推断，未实际安装验证） |

成本参数可以参考：moomoo AU 美股每单 US$0.99，另有转嫁费；澳元兑美元的换汇点差约 0.5%–0.55%，各来源不一致 ([moomoo AU 美股页](https://moomoo.com/au/invest/us-stock)、[moomoo vs Stake](https://www.moomoo.com/au/learn/moomoo-vs-stake)【中】)。小额频繁交易时，换汇才是主要摩擦，建议一次性换汇后长期持有美元现金（推断）。税务方面，提交 W-8BEN 后美股股息预扣 15% ([expattaxes](https://www.expattaxes.com.au/how-us-international-shares-taxed-australia/)【低】)。外国税抵免（FITO）只能抵扣计入澳洲应税收入的那部分，享受 50% CGT 折扣的资本利得只能按一半对应抵免 ([ATO](https://www.ato.gov.au/forms-and-instructions/foreign-income-tax-offset-rules-guide-2010/when-a-foreign-income-tax-offset-applies/foreign-income-tax-must-have-been-paid-on-assessable-income)【高】、[Public Accountant](https://publicaccountant.com.au/news/court-backs-ato-position-on-foreign-income-tax-offsets/)【中】)。所以高换手的策略在应税账户里还会额外损失 CGT 折扣（推断）。

### 按优先级排序的回测清单

排序原则是：证据强、实现简单、数据好拿的排在前面，因为前几步的作用是验证系统本身是否可信，而不是马上找 alpha。

| 优先级 | 回测任务 | 目的 / 通过标准 | 依据 |
|---|---|---|---|
| 0 | 系统校准：用 Qlib 和 vectorbt 复现沪深300、SPY 的买入持有，以及一个已知的 Faber 10 个月均线结果 | 和公开数字误差足够小；分别打开和关闭涨跌停、T+1、滑点，量化这些设置对结果的影响 | [exchange.py](https://github.com/microsoft/qlib/blob/main/qlib/backtest/exchange.py)、[Concretum](https://concretumgroup.com/global-tactical-asset-allocation/) |
| 1 | 双市场 ETF 资产配置基准：A股宽基 + 红利 + 国债 + 黄金，美股 SPY + IEF/TLT + GLD；对比等权、风险预算、60/40；以澳元计价 | 得到一个"不做选股也能接受"的基准；测试月初、月中、月末不同调仓日 | [S&P Global](https://www.spglobal.com/en/research-insights/articles/the-potential-value-of-u-s-equity-allocation-to-chinese-investors)、[ThinkAdvisor](https://thinkadvisor.com/2022/10/17/is-the-6040-portfolio-dead-or-just-resting) |
| 2 | 在第 1 步上叠加趋势过滤（10 个月均线 / 3-6-9-12 月动量平均，分批调仓） | 检验能否显著降低 2015、2018、2022 年的回撤，以及代价是牛市跑输多少 | [Cambridge Associates](https://www.cambridgeassociates.com/insight/does-trend-followings-recent-struggle-signal-that-the-strategy-is-structurally-broken/)、[Newfound](https://blog.thinknewfound.com/2013/08/the-luck-of-the-rebalance-timing/) |
| 3 | A股红利低波：用指数复现，再自建（股息率 + 低波，剔除 ST） | 对照中证官方数据核实 13.75% / -22.1%；检验拥挤以后的表现 | [界面新闻](https://m.jiemian.com/article/14715469.html) |
| 4 | 美股只做多的价值、质量、动量单因子及组合（大中盘，NYSE 分位点，季度调仓，带 buy/hold spread），先用 Ken French / AQR 数据校准 | 多因子组合扣费后超额为正，成本 ×2 仍为正，t 值接近 3 | [Novy-Marx & Velikov](https://nber.org/papers/w20721)、[AQR Datasets](https://www.aqr.com/insights/datasets) |
| 5 | A股只做多多因子：EP、低异常换手、低波、盈利，剔除最小 30% 市值和 ST、*ST，分 2000–2016（样本内）和 2017 年至今（样本外） | 样本外是否保留了样本内的一半以上；分年度看 2024 年初的回撤 | [LSY](https://faculty.wharton.upenn.edu/wp-content/uploads/2018/03/Size-and-Value-in-China.pdf)、[中证网](https://www.cs.com.cn/xwzx/hg/202404/t20240418_6403005.html) |
| 6 | A股 1 个月反转（严格执行 T+1 和涨跌停，分析跌停导致无法卖出的情况） | 扣实际费率后是否仍为正；跌停股占比有多高 | [LSY](https://faculty.wharton.upenn.edu/wp-content/uploads/2018/03/Size-and-Value-in-China.pdf) |
| 7 | A股宽基/行业 ETF 动量轮动（只用长窗口，参数粗粒度、多窗口平均） | 目前没有权威证据，只做探索；必须计入试验登记表 | [CSDN（反例）](https://gitcode.csdn.net/69eb21d254b52172bc6fc38b.html) |
| 8 | 小市值轮动（只作为风险研究） | 量化 2024 年初那种风险；作为反例理解拥挤平仓 | [复旦](https://fddi.fudan.edu.cn/2b/23/c21253a666403/page.htm) |
| 9 | 机器学习（Qlib Alpha158 + LightGBM，purged CV）和 LLM 特征 | 只有在 0–5 步都稳定之后再做；LLM 特征只用模型知识截止日之后的数据检验 | [Glasserman & Lin](https://arxiv.org/abs/2309.17322) |
| 贯穿 | 模拟盘至少数月（经验推断，没有权威标准），对比回测和模拟盘的成交价与滑点偏差 | 偏差可以解释之后才考虑小资金实盘 | — |

### 需要你亲自核实的事项

| 事项 | 为什么需要你核实 | 怎么核实 |
|---|---|---|
| 银河 QMT / miniQMT / PTrade 的开通门槛、费用、佣金下限 | 二手说法从"无门槛"到 10 万、50 万、300 万元都有，客户经理有压低门槛的动机 ([叩富网](https://licai.cofool.com/ask/vipqa_7311004_43391200.html)【低】) | 在银河 App"业务办理"或向营业部索取书面答复，包括零售佣金费率 |
| 境外居住者能否远程开通、登录 QMT，是否有 IP 限制，以及境外居住者做程序化交易的合规问题 | 子调研没有找到任何来源 | 直接问银河客服；同时确认程序化交易报告需要填哪些字段 |
| 银河"玉衡"是否面向零售 | 无法核实 | 问客户经理 |
| moomoo AU OpenAPI 实测：美股实盘下单、模拟盘、下单限频、行情等级与收费、能否交易 ASX | 官方文档的表格解析存在冲突；旧文档写下单限频为每 30 秒 15 次，未核实 ([moomoo AU](https://www.moomoo.com/au/support/topic3_436)) | 安装 OpenD 和 Python SDK（包名 `moomoo-api`，未核实），先用模拟盘跑通查询、下单、撤单 |
| 换汇点差和转嫁费 | 0.5% 和 0.55% 两种说法 ([moomoo vs CommSec](https://www.moomoo.com/au/learn/moomoo-vs-commsec)) | 小额实测一笔换汇，看结单 |
| A股现行印花税、各板块涨跌幅、最小手数、ETF 是否 T+0 | 子调研没有拿到条文原文 | 查沪深交易所交易规则和财政部公告 |
| 红利低波的官方年化和回撤 | 现有数字是媒体转述 | 查中证指数公司的指数资料 |
| 数据源能否覆盖退市股、财务数据是否按公告日对齐 | 子调研没有找到可靠资料 | 用几只已知的退市股，分别在 BaoStock、Tushare、AKShare 上实测 |
| 能否通过 UNSW 的 WRDS 访问 CRSP、Compustat | 未核实 | 问 UNSW 图书馆 |
| 澳洲税务：A股收益的申报、中国股息预扣与 FITO、会不会被认定为 share trader | 只拿到了高层次的资料 | 咨询注册税务师 |
| 资金规模和最大可承受回撤 | 决定候选策略的权重和是否值得做个股 | 你自己定一个数字（例如"账户回撤到 X% 时我还能坚持"） |

## 风险与局限声明

本报告不是投资建议，作者不是持牌金融顾问，也不替你选定任何策略。所有历史收益和回撤都来自回测或过去的实盘，**回测不等于未来**：发表后的因子平均缩水约一半 ([CXO Advisory](https://www.cxoadvisory.com/big-ideas/effects-of-market-adaptation))，而且你自己试的参数越多，回测结果越不可信 ([Bailey et al.](https://www.davidhbailey.com/dhbpapers/overfitting.pdf))。

报告本身有几处明确的局限。第一，A股学术证据的样本截止到 2016 年，2017 年以后的因子样本外数据、券商金工报告的 IC 和 IR，都没有拿到一手来源。第二，表中的"预期扣费收益区间"是推断，不是来源给出的数字。第三，红利低波、因子 ETF 和 CTA 的部分数字来自媒体或比价站，口径不统一。第四，2026 年的市场数据大多是低可信度来源。第五，银河 QMT 的门槛、跨境使用、moomoo 的限频和行情收费，都没有官方的一手确认。第六，汇率（澳元计价）和澳洲税务对净收益的影响没有做定量分析。

杠杆、期权、高频和小盘集中持仓都会把上面讨论的回撤数字放大，任何策略都可能出现超过历史最大值的回撤。

## 结论

这次调研最有用的发现，不是哪个策略"最赚钱"，而是**证据强度和可执行性在两个市场里是错位的**。美股的因子证据最厚，但只做多的因子组合本质上还是股票 beta，超额有限。A股的因子在统计上更强（EP 的 t 值约 4，反转的年化 alpha 18%），但这些收益恰好集中在 T+1、涨跌停、不能做空和拥挤踩踏最伤人的地方。所以对你来说，第一阶段真正可以建立的优势，大概率不是 alpha，而是**纪律**：一个按澳元计价、跨两个市场的低换手配置基准，加上趋势风控，再加上一套诚实的验证流程（试验登记表、DSR/PBO、成本翻倍测试、调仓日敏感性）。在这个基础上再去检验 A股的多因子和美股的因子倾斜，才能分清哪些超额是真的，哪些是回测出来的。

第二个启示是，工程上的默认值本身就是风险。Qlib 不限涨跌停、不计滑点，yfinance 没有退市股，moomoo 的小资金额度拉不到全市场历史，miniQMT 需要 Windows。这些问题不处理，任何回测数字都没有意义。建议先完成回测清单的第 0 步（系统校准）和核实清单里关于券商接口的几项，再谈具体策略。
