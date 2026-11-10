# 美股系统化股票策略的长期证据（个人投资者可实施版）

> 调研日期：2026-10-30。范围：美股。凡标“二手”的数字来自综述或博客，不是原论文，回测前应回到原始数据（Ken French Data Library、AQR Datasets）核对。

## 问题 1：主要因子的长期溢价、发表后衰减与“复制危机”

### Takeaway
多数经典因子（价值、动量、质量/盈利、低贝塔）在学术意义上能被复制，但发表后收益平均缩水约一半以上；按市值加权并剔除微盘股后，大量“异象”不再显著。规模（size）是最弱的一个，单独做几乎没有溢价，叠加质量控制后才有。

### Cited Findings
**发表后衰减（McLean & Pontiff 2016, Journal of Finance）**
- 97 个已发表收益预测因子：样本内多空月均毛收益 0.58%，样本外但发表前 0.40%（低 26%），发表后（至 2013 年）0.26%（低 58%）；作者把其中约 32 个百分点归因于发表后的套利交易 — [CXO Advisory 综述](https://www.cxoadvisory.com/big-ideas/effects-of-market-adaptation)
- 衰减最快出现在发表后第 3–4 年；样本外头 12 个月平均没有衰减；97 个里有 12 个达不到发表时宣称的 95% 置信度；样本内收益越高、t 值越高、只用技术面（价格）数据的因子衰减越大 — [CXO Advisory](https://www.cxoadvisory.com/big-ideas/effects-of-market-adaptation)
- 注意：上面的百分比和四舍五入后的月收益对不上（0.58→0.26 约等于 55%），推测原文用的是未四舍五入的数据 — [CXO Advisory](https://www.cxoadvisory.com/big-ideas/effects-of-market-adaptation)
- 后续研究：一项复制研究发现 Sharpe 比率下降约 43%，略小于 McLean-Pontiff 的 58%；另一篇 2022 年论文估计衰减随时间累积（样本结束后 3 年约 -25%，5 年约 -40%，10 年约 -50%），并认为发表偏差只解释约 12% 的衰减，其余是预期收益真的变了 — [arXiv 2209.13623 Publication Bias in Asset Pricing Research](https://arxiv.org/pdf/2209.13623)；[arXiv 2105.01380 Why and how systematic strategies decay](https://arxiv.org/pdf/2105.01380)
- 以上收益都是毛收益，没扣交易成本和融券成本 — [CXO Advisory](https://www.cxoadvisory.com/big-ideas/effects-of-market-adaptation)

**复制危机：Hou, Xue & Zhang "Replicating Anomalies"（RFS）**
- 447 个异象中，用 NYSE 分位点加市值加权（压低微盘股影响）后，286 个（64%）在 5% 水平不显著；门槛提高到 t≥3 时，380 个（85%）不显著。即使显著的那些，幅度也常常远低于原文 — [NBER w23394](https://www.nber.org/papers/w23394.pdf)；[Alpha Architect 综述](https://alphaarchitect.com/replicating-anomalies/)
- 微盘股占股票数量的大多数，但只占很少的市值，这是结论和早期文献不同的主要原因 — [Bloomberg 报道](https://www.bloombergquint.com/markets/forget-factors-paper-says-most-market-anomalies-are-imaginary)
- （常被引用的“452 个 / 65%”与已发表版本不一致，以 447 / 64% 为准。）

**反方：Jensen, Kelly & Pedersen "Is There a Replication Crisis in Finance?"（Journal of Finance 2023, vol.78, pp.2465–2518）**
- 用贝叶斯框架，在 93 个国家的 153 个因子上检验：多数因子可复制，可归为 13 个主题，并且在全球样本中样本外有效；13 个主题中有 10 个复制率超过 75%，例外是 Seasonality、Leverage 和 Size — [NBER w28432](https://www.nber.org/papers/w28432)；[CBS 出版版 PDF](https://research-api.cbs.dk/ws/portalfiles/portal/95651880/theis_ingerslev_jensen_et_al_is_there_a_replication_crisis_in_finance_publishersversion.pdf)；[Alpha Architect](https://alphaarchitect.com/is-there-a-replication-crisis-in-finance/)
- 二手综述：贝叶斯口径下 CAPM alpha 显著的比例约 85%，各市值分组都有较高复制率 — [Alpha Architect](https://alphaarchitect.com/is-there-a-replication-crisis-in-finance/)

**规模（Size）**
- Alquist, Israel & Moskowitz "Fact, Fiction, and the Size Effect"（JPM 2018）：即使在原始发现期，规模效应也不强（和价值、动量比）；大量发表之后小盘策略没有显著正溢价；24 个国际市场也没有一致的正溢价 — [AQR PDF](https://www.Aqr.Com/-/media/AQR/Documents/Whitepapers/Fact-Fiction-and-the-Size-Effect.pdf?sc_lang=en)；[Alpha Architect](https://alphaarchitect.com/fact-fiction-and-the-size-effect/)
- 引用 DFA 数据：1982–2017 年美股规模溢价算术平均每年 0.9%，几何年化 0.0% — [Advisor Perspectives](https://www.advisorperspectives.com/articles/2018/07/12/the-size-effect-is-not-dead)
- 作者认为表现不稳定主要来自垃圾股，控制质量后规模溢价恢复（注意：作者是 AQR，有商业立场） — [ETF.com Swedroe](https://www.etf.com/sections/index-investor-corner/swedroe-rediscovering-size-effect)

**质量 / 低贝塔**
- Asness, Frazzini & Pedersen "Quality Minus Junk"：QMJ 在美国和另外 24 个国家都有显著风险调整收益；AQR 公开更新 BAB 和 QMJ 数据集（BAB 覆盖美国和 23 个国际市场，数据到 2026 年 7 月） — [AQR QMJ](https://www.aqr.com/Insights/Research/Working-Paper/Quality-Minus-Junk?aqrPDF=1)；[AQR Datasets](https://www.aqr.com/insights/datasets)
- 独立检验（Bradrania, Veron & Wu 2023）：22 个国家里 14 个有贝塔异象，异象集中在低质量股，在高质量股里不存在；加入 QMJ 后 BAB 的 alpha 消失，说明低贝塔与质量高度重叠 — [Adelaide 数字图书馆](https://digital.library.adelaide.edu.au/items/ea6b10cd-d450-4b70-b2f1-c66fdfc824f4/full)
- 斯塔万格大学硕士论文把 QMJ 扩展到 44 个国家，结果仍为正且显著（证据力度有限） — [UiS Brage](https://uis.brage.unit.no/uis-xmlui/handle/11250/2682140?show=full)

### Inferences
- 回测因子时，预期收益应按“论文数字 × 约 0.4–0.5”打折，再扣成本；样本外收益约为样本内的一半是合理的先验。
- 优先选：经济逻辑清楚、换手低、不依赖微盘股、在 JKP 的 13 个主题中复制率高的（价值、动量、质量/盈利、低风险）；单独的规模因子和季节性因子应降低优先级。
- 回测必须用 NYSE 分位点和市值加权（或至少剔除微盘股），否则会复现 Hou-Xue-Zhang 批评的那种虚高。

### Gaps
- 没有拿到各因子（HML、UMD、RMW、BAB、QMJ）全样本的年化收益、Sharpe 和最大回撤的一手数字；需从 Ken French Data Library 和 AQR Datasets 下载计算。
- Novy-Marx (2013) gross profitability 的原文数字和发表后表现没有找到可靠来源。
- BAB 的具体 Sharpe 比率没有找到一手来源。

## 问题 2：最差时期——2009 动量崩溃、2018–2020 价值回撤、2022–2026 近况

### Takeaway
动量的尾部风险是“熊市后急反弹”时空头腿被轧（2009 年多空动量 3 个月约 -73%）；价值在 2017–2020 年经历了有记录以来最大回撤（约 -42%～-59%，看口径）。2026 年因子表现分化：价值领先，低波和质量在 Q3 落后，动量在 6 月见顶后大跌。

### Cited Findings
**动量崩溃（Daniel & Moskowitz "Momentum Crashes", JFE 2016，样本 1927–2013）**
- 2009 年 3–5 月，过去输家组合上涨约 156%–163%，赢家组合只涨约 8%（不同版本数字略有差异）；崩溃发生在大跌后的市场反弹期，主要亏在空头腿 — [NBER w20439](https://www.nber.org/system/files/working_papers/w20439/w20439.pdf)；[Columbia 工作论文](https://business.columbia.edu/sites/default/files-efs/pubfiles/4607/mom11.pdf)
- 多空动量 2009 年约 3 个月回撤 -73% 左右，这个数来自二手来源，原论文里没有直接写 -73% — [ETF.com Swedroe](https://www.etf.com/sections/index-investor-corner/swedroe-downside-momentum)；[Alpha Architect](https://alphaarchitect.com/avoiding-momentum-crashes/)
- 注意 -73% 是多空组合；只做多的动量组合回撤小得多（见问题 3 ETF 数据）。

**价值的“量化寒冬”**
- HML 从 2017 年 1 月到 2020 年 3 月回撤约 42%；从 2007 年 1 月算起约 51%，为历史最大；用单变量价值排序则分别是 47% 和 59%（二手：Buckingham 对 AQR 研究的综述） — [Alpha Architect](https://alphaarchitect.com/do-interest-rates-explain-values-underperformance/)
- 2020 年 Q1 被称为价值投资者史上最差季度 — [Institutional Investor](https://www.institutionalinvestor.com/article/2bsxa6cu6tic60cll6g3k/portfolio/value-managers-fight-back)
- AQR（Israel, Laursen & Richardson 2020）检验了 5 种解释，认为都站不住；Asness（2020-05-08）认为是贵股和便宜股之间估值价差脱离基本面，并非结构性失效（AQR 是利益相关方） — [AQR JPM 文章](https://www.aqr.com/Insights/Research/Journal-Article/Is-Systematic-Value-Investing-Dead)；[Cliff's Perspective PDF](https://www.aqr.com:443/-/media/AQR/Documents/Perspectives/Cliffs-Perspective-5620-Is-Systematic-Value-Investing-Dead.pdf?sc_lang=en)
- 已有专门文章总结 AQR 在 2018–2020 年经历的量化危机 — [Institutional Investor](https://institutionalinvestor.com/article/2dqsr456gmu55p19gxiio/corner-office/cliff-asness-has-steered-hedge-fund-aqr-through-not-one-not-two-but-three-quant-crises)

**2026 年近况**
- 2026 Q3（S&P 500 因子指数，价格收益）：Value +0.19%，Momentum -2.42%，Quality -5.48%，Low Volatility -6.26%，S&P 500 +2.25%；动量在 6 月下旬见顶后大幅回落 — [CME Group（搜索摘要，全文抓取超时）](https://www.cmegroup.com/articles/2026/factors-2026-q3-review-q4-outlook-with-factor-futures.html)
- 2026 Q2：全球范围动量最好（主要靠科技/半导体暴露），低波最差；美国规模排第二 — [Morningstar Factor Monitor Q2 2026](https://indexes.morningstar.com/insights/markets-review/blt49b23cb4e87c0d8d/morningstar-factor-monitor-q2-2026)
- 2026 Q1：全球价值最好，质量最差 — [Morningstar Factor Monitor Q1 2026](https://indexes.morningstar.com/insights/Markets%20Review/blte89f9f7a346c4d62/morningstar-factor-monitor-q1-2026)
- 年初至今 ETF 数字各来源不一致（例如 VLUE +48.6% 和 MTUM +27.4%，另一来源 MTUM +22.4%），可信度低 — [DataPorium](https://dataporium.tech/articles/factor-investing-in-2026-value-quality-momentum-and-low-volatility-results-so-far)；[Brimind](https://brimindinvest.com/blog/factor-investing-guide-2026)
- Fama-French 的官方数据库从 2025 年 1 月起改用基于新版 CRSP 的文件，和早年数据的可比性可能受影响 — [Ken French Data Library](http://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)

### Inferences
- 动量 2026 年 6 月后的下跌和高度集中在半导体有关，属于行业集中风险，不同于 2009 年那种空头被轧的崩溃（推断）。
- 价值在 2017–2020 年熬了 3 年多、回撤约一半，个人投资者要按“可能连续 3–5 年跑输”来准备心理和仓位。
- 价值和动量负相关，组合起来能显著平滑最差时期（与下文 Frazzini 等的“价值+动量”容量结论一致）。

### Gaps
- 2022–2025 年 HML、SMB、UMD、RMW 的年度数字没有拿到一手值（YCharts 只有月度序列，标注为“benchmark”，可能和 French 官方不同）。需下载 French 年度文件计算。
- 2026 年 MTUM 具体回撤幅度未核实。

## 问题 3：只做多 vs 多空——20–50 只股票或因子 ETF 能拿到什么；成本、换手、税

### Takeaway
多头腿贡献了几乎全部规模溢价、约 60% 的价值溢价和约一半的动量收益，所以只做多能保留相当一部分溢价。机构真实成本远低于学术估计，但这基于 AQR 级别的执行。月换手低于约 50% 的策略多数能在扣成本后存活。因子 ETF 实盘自 2013 年以来都跑赢了 SPY，但回撤和大盘差不多。

### Cited Findings
**多空拆分**
- Israel & Moskowitz (JFE 2013)：多头部分占规模溢价的几乎全部、价值的 60%、动量的一半；公司越小，价值越依赖空头，动量越不依赖空头；在 86 年美股数据中稳健 — [AQR](https://www.aqr.com/Insights/Research/Journal-Article/The-Role-of-Shorting-Firm-Size-and-Time-on-Market-Anomalies)；[RePEc](https://ideas.repec.org/a/eee/jfinec/v108y2013i2p275-301.html)

**交易成本**
- Novy-Marx & Velikov "A Taxonomy of Anomalies and Their Trading Costs"（RFS 2016, 29(1):104–147）：月换手低于约 50% 的异象，在为降低成本而设计时多数仍有显著净收益，高换手的很少；最有效的单一降本方法是设“买入/持有差”（buy/hold spread，入场门槛比继续持有门槛高） — [NBER w20721](https://nber.org/papers/w20721)；[作者 PDF](https://mysimon.rochester.edu/novy-marx/research/ToAatTC.pdf)
- Frazzini, Israel & Moskowitz "Trading Costs"：AQR 19 年、21 个发达市场、约 1.7 万亿美元的真实成交数据；实际成本比以往研究低一个数量级；大单和小盘股成本更高；美股 size/value/momentum 多空因子的盈亏平衡规模约为 1030 亿、830 亿、520 亿美元；价值+动量组合约 1000 亿（美国），因交易对冲 — [SSRN 3229719](https://papers.ssrn.com/abstract=3229719)；[NBER 会议稿](https://conference.nber.org/conf_papers/f68262/f68262.pdf)；[Alpha Architect](https://alphaarchitect.com/surprise-the-size-value-and-momentum-anomalies-survive-after-trading-costs/)
- 反方：Lesmond, Schill & Zhou (2004) 认为动量利润被成本吃掉；Korajczyk & Sadka 估计动量容量仅约 50 亿美元；有说法称动量指数化策略在 100 亿美元 AUM 时成本可达 200bp 以上 — [Alpha Architect](https://alphaarchitect.com/surprise-the-size-value-and-momentum-anomalies-survive-after-trading-costs/)；[Advisor Perspectives](https://api.advisorperspectives.com/articles/2019/06/20/how-trading-costs-erode-factor-returns)
- 也有文章认为交易成本会摧毁因子投资 — [Alpha Architect "Trading costs destroy factor investing"](https://alphaarchitect.com/trading-costs-destroy-factor-investing/)

**因子 ETF 实盘（非学术、口径不统一）**
- PortfoliosLab“全部历史”年化（各基金起始日不同）：MTUM 15.19%、QUAL 13.59%、USMV 11.89%、VLUE 13.41%，SPY 10.80% — [PortfoliosLab MTUM](https://portfolioslab.com/symbol/MTUM)
- 2013-07 至 2026-10 中旬累计总收益：MTUM +549.72%，QUAL +450.93%，VLUE +394.34%（无 SPY 对照） — [TotalRealReturns](https://totalrealreturns.com/n/MTUM,QUAL,VLUE)
- 2020-03 最大回撤：MTUM、QUAL 约 -34%，VLUE 约 -39%，和大盘回撤相近 — [TotalRealReturns](https://totalrealreturns.com/n/MTUM,QUAL,VLUE)
- AVUV（Avantis 美股小盘价值，2019-09-24 成立，费率 0.25%）：截至 2021-08-31 成立以来 NAV 收益 25.33% — [SEC N-CSR FY2021](https://www.sec.gov/Archives/edgar/data/1710607/000171060721000147/acetf8312021n-csr.htm)；某比较站称 5 年 AVUV 13.90% 对 IWN 9.49%（未注明日期） — [比较站](https://swingtradebot.com/etf-comparison/AVUV-vs-IWN)；AVUV 成立以来最大回撤 -49.42%（2020 年），IWN -61.55%（IWN 2000 年成立，包含 2008 年，期间不可比） — [PortfoliosLab](https://portfolioslab.com/tools/stock-comparison/AVUV/IWN)

### Inferences
- 个人做 20–50 只股票的只做多组合：能拿到的是“多头腿溢价减去市场贝塔以外的跟踪误差”，大致保留价值的六成、动量的一半；规模几乎全部在多头，但规模本身溢价弱。
- 个人资金量很小，市场冲击可以忽略，主要成本是买卖价差和税；选低换手设计（季度或半年调仓、buy/hold spread、大中盘股票池）。
- 动量换手最高，在美国应税账户中短期资本利得税会明显侵蚀收益；价值和质量换手低、更适合应税账户（推断，没有找到量化税负的来源）。
- ETF 实盘数据只覆盖 2013 年以来、且恰逢美股大牛市；它们“跑赢 SPY”有一部分可能是风格暴露（MTUM 偏科技）而不是因子溢价。

### Gaps
- 没找到量化“因子策略税负拖累”的一手研究。
- 没找到同一截止日的 MTUM/QUAL/USMV/VLUE/AVUV 与 SPY 的规范比较（应用 iShares/Avantis 官网 factsheet 统一日期核对）。
- 没找到集中持仓（20–50 只）相对全市场分位数组合的跟踪误差研究。

## 问题 4：简单择时叠加——Faber 10 个月均线、Antonacci 双动量

### Takeaway
两者主要作用是降低深度熊市回撤（2000–02、2008）；但证据多为样本内或博客复现，择时“技巧”统计上不显著，快速崩盘（如 2020 年 3 月）月度信号来不及反应，牛市里会因为反复进出明显跑输（whipsaw）。

### Cited Findings
- 独立在 SPY 上复现 Faber 10 个月均线：33 年 23 次往返交易；最大回撤不到 SPY 的一半；但胜率置信区间包含 50%，随机日期进出效果差不多；最近 3 年该规则年化 12.9%，SPY 22.3% — [empiricalab Substack](https://empiricalab.substack.com/p/faber-10-month-average)
- “调仓时点运气”：Faber 模型隐含在每月第一个交易日交易，换个日期结果差异很大 — [Flirting with Models (Newfound, 2013)](https://blog.thinknewfound.com/2013/08/the-luck-of-the-rebalance-timing/)
- 论坛讨论：均线可能造成接二连三的 whipsaw — [Bogleheads](https://www.bogleheads.org/forum/viewtopic.php?t=173272)
- 双动量（GEM）用 12 个月收益而不是均线作为绝对动量，实践者认为二者差别不大 — [Gyroscopic Investing 论坛](https://www.gyroscopicinvesting.com/forum/viewtopic.php?t=7949)；[Bogleheads 双动量帖](https://www.bogleheads.org/forum/viewtopic.php?t=158297&start=200)
- 博客称 2014–2022 年 GEM 跑输 S&P 500 买入持有，原因是频繁的假信号和交易成本（未用一手数据核实） — [reblnc](https://reblnc.com/insights/dual-momentum)
- 对双动量的批评，包括数据挖掘和样本外担忧 — [A Wealth of Common Sense (2015)](https://awealthofcommonsense.com/2015/07/my-thoughts-on-gary-antonaccis-dual-momentum/)

### Inferences
- 这类规则更像是“买保险”：长期收益可能略低于持有，但避开了深度熊市的大部分跌幅；适合不能承受 -50% 回撤的人，而不是想提高收益的人。
- 回测时必须测试不同调仓日（月初、月中、月末），并在应税账户里计入卖出产生的资本利得税。

### Gaps
- 没找到同行评审的 Faber/GEM 样本外检验；Faber 原始 SSRN 论文的具体数字未核实。
- 2014 年以来 GEM 的实盘或一手回测数字未核实。

## 问题 5：短期反转（1 个月 / 周）在美股是否能扣成本后存活

### Takeaway
传统 1 个月反转扣成本后基本为零；能存活的版本是只在大盘股里做、控制换手，或用剔除因子暴露后的“残差反转”。个人投资者在零佣金下仍要付买卖价差，高频换手风险很大。

### Cited Findings
- 多项研究认为传统短期反转扣成本后利润基本消失；Blitz 等的检验显示传统策略净收益和零没有显著差异；残差反转（按剔除因子暴露后的收益排序）在 1990 年后、仅限大盘股样本中，扣成本后仍显著 — [CEPR DP15857](https://repec.cepr.org/repec/cpr/ceprdp/DP15857.pdf)；[EUR Repub](https://repub.eur.nl/pub/40707)
- AQR 真实成交数据：短期反转在美国超过 90 亿美元、全球超过 130 亿美元规模后无法覆盖成本 — [NBER 会议稿 Frazzini-Israel-Moskowitz](https://conference.nber.org/conf_papers/f68262/f68262.pdf)
- De Groot, Huij & Zhou：成本问题主要来自小盘股；只在最大的美股中做，换手和成本减半以上，近十年大盘股净反转收益显著为正 — [EFMA 2011 论文](https://efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2011-Braga/papers/0259_update.pdf)；[EFMA 2012](https://www.efmaefm.org/0EFMSYMPOSIUM/2012/papers/017_update.pdf)
- 反转收益常被解释为提供流动性的报酬，主要出现在市场大跌后的几周 — [Quantpedia](https://quantpedia.com/strategies/short-term-reversal-in-stocks)

### Inferences
- 个人资金小，市场冲击不是问题，但价差和应税账户的短期资本利得税是主要障碍；只有在免税账户、大盘股、残差反转、低换手控制下才值得回测。
- 反转收益集中在大跌后，带有“接飞刀”的尾部风险，与动量崩溃同一时期可能对冲（推断）。

### Gaps
- 没找到针对零佣金时代散户实际价差的反转净收益研究。
- 没找到 2015 年后美股大盘股反转的最新样本外数字。
