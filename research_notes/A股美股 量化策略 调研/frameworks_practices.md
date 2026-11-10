# 量化研究流程最佳实践 + 开源框架对比（A 股 + 美股，个人 Python 开发者视角）

> 调研时间：2026-10-30。仓库星数、最近提交、版本号均为当天通过 GitHub API / PyPI JSON API 实时抓取。
> 说明：SSRN 页面对抓取返回 403，相关论文信息来自 NBER / arXiv / 期刊索引页 / 搜索摘要；凡是只经二手摘要确认的，均已标注。

## 问题 1：防过拟合的验证最佳实践

### Takeaway
学术与业界的共识是：回测"好看"很容易，难的是证明它不是多重检验后的运气。最低要做到四件事：记录试过多少个变体并用 DSR / PBO 折算；新因子 t 值门槛提高到 3 左右；时间序列交叉验证要做 purge + embargo；预期样本外收益会比样本内明显打折，发表后的因子衰减还更大。

### Cited Findings
**回测过拟合概率（PBO）**
- Bailey、Borwein、López de Prado、Zhu 的论文 "The Probability of Backtest Overfitting" 发表于 Journal of Computational Finance 第 20 卷第 4 期（DOI 10.21314/JCF.2016.322）。期刊页标注 2017 年，SSRN 预印本标注 2015 年 forthcoming，两处日期不一致 — [Risk.net](https://www.risk.net/journal-of-computational-finance/2471206/the-probability-of-backtest-overfitting)；[SSRN](https://papers.ssrn.com/abstract=2326253)
- 论文提出用"组合对称交叉验证"（CSCV）估计 PBO，并指出 hold-out 等传统防过拟合方法在投资回测场景里"不可靠且不准确" — [Risk.net](https://www.risk.net/journal-of-computational-finance/2471206/the-probability-of-backtest-overfitting)；全文 PDF：[eScholarship](https://escholarship.org/content/qt4w1110bb/qt4w1110bb.pdf)
- 同一作者组的相关工作指出：只要试过的策略变体相对数据量偏多就构成过拟合，而且只需试相对少量的配置，就能得到很高的回测表现 — [Bailey et al., davidhbailey.com](https://www.davidhbailey.com/dhbpapers/overfitting.pdf)；[JOIM 2017](https://joim.com/wp-content/uploads/emember/downloads/p0542.pdf)

**通缩夏普比率（Deflated Sharpe Ratio, DSR）**
- Bailey & López de Prado (2014)，"The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality"，Journal of Portfolio Management 40(5): 94–107 — [SSRN](https://papers.ssrn.com/abstract=2460551)
- DSR 同时修正两种夏普虚高：一是从多个策略里挑最好的那个造成的选择偏差，二是收益分布的偏度和峰度。输入包括样本长度、试验次数、各试验夏普比率的方差。只试过一个策略时，DSR 就等于 PSR（Probabilistic Sharpe Ratio，只修正非正态和样本长度）（二手摘要） — [CXO Advisory](https://cxoadvisory.com/big-ideas/sharper-sharpe-ratio)；[tradingstrategy.ai PSR 词条](https://tradingstrategy.ai/glossary/probabilistic-sharpe-ratio)
- 实操难点在"试验次数"怎么算：各试验之间相关，有效次数会少于字面次数，最后往往要靠判断 — [MetricGate 文档](https://metricgate.com/docs/deflated-johnson-sharpe-ratio/)
- R 的 quantstrat 包已内置 `deflatedSharpe` 函数 — [rdocumentation](https://www.rdocumentation.org/packages/quantstrat/versions/0.16.7/topics/deflatedSharpe)

**Harvey-Liu-Zhu 的 t > 3 门槛**
- Harvey、Liu、Zhu，"...and the Cross-Section of Expected Returns"，NBER WP 20592（2014），后刊于 RFS 2016。论文认为已有数百个因子被提出，传统 |t| > 2 不再合适；用多重检验框架估算后，新因子应达到 t > 3.0，并认为金融经济学中多数已发表的发现可能是假的 — [NBER](https://www.nber.org/papers/w20592)

**样本外衰减与发表后衰减**
- McLean & Pontiff（Journal of Finance 2016）研究 97 个横截面预测变量：样本外多空收益平均下降 26%（作者视为统计偏差/数据挖掘影响的上界），发表后平均下降 58%，差值约 32% 归因于投资者按论文交易 — [CFA Institute 摘要](https://rpc.cfainstitute.org/research/cfa-digest/2016/06/does-academic-research-destroy-stock-return-predictability-digest-summary)；[论文 PDF](https://Www.Gwern.net/doc/economics/2016-mclean.pdf)
- 反方证据（作者有 AQR 背景）：Jensen、Kelly、Pedersen 的 "Is There a Replication Crisis in Finance?"（NBER WP 28432，2021；刊于 JF 2023）用贝叶斯框架评估 93 国、153 个因子，结论是多数因子能复现，且在新数据上样本外仍有效；代码和数据公开 — [NBER](https://www.nber.org/papers/w28432)
- 二手摘要称，13 个主题中有 10 个复现率超过 75%，例外是 Seasonality、Leverage、Size（未与原文核对） — [Alpha Architect](https://alphaarchitect.com/is-there-a-replication-crisis-in-finance/)

**Purged K-fold / Embargo / CPCV**
- Purged CV 是 López de Prado 于 2017 年提出的 k-fold 变体：删除训练集中与测试集标签区间重叠的样本（purge），再在测试集之后留一段时间缓冲（embargo），防止前视泄漏 — [Wikipedia: Purged cross-validation](https://en.wikipedia.org/wiki/Purged_cross-validation)
- 《Advances in Financial Machine Learning》第 7 章讲 purging 和 embargo，第 12 章讲 CPCV（组合清洗交叉验证）。CPCV 从 N 个分组中生成所有训练/测试组合，得到绩效的分布而不是单条路径（二手） — [tradingstrategy.ai 方法论](https://tradingstrategy.ai/docs/learn/backtesting.html)；[temporalcv 文档](https://temporalcv.readthedocs.io/en/latest/api/cv_financial.html)
- 一份从业者指南给出经验法则：embargo 不少于标签持有期的 2 倍。这是启发式做法，并非原论文给出 — [tradingstrategy.ai](https://tradingstrategy.ai/docs/learn/backtesting.html)
- López de Prado 的"ML 基金失败原因"演讲（Quantpedia 版列出 7 条，JPM 2018 论文版称 10 条，数量有出入）里包括"交叉验证泄漏"和"回测过拟合" — [Quantpedia](https://quantpedia.com/why-machine-learning-funds-fail/)

**交易成本与 A 股撮合约束（以 Qlib 源码为例）**
- Qlib `Exchange` 默认参数：`open_cost=0.0015`、`close_cost=0.0025`、`min_cost=5.0`、`impact_cost=0.0`（注释称"冲击成本/滑点，推荐值 0.1"）；`trade_unit` 在 A 股为 100 股；`limit_threshold` 默认 None，即不限制。当 region 为 CN/TW 且未设置时会警告"涨跌停股票可能被买卖" — [qlib/backtest/exchange.py](https://github.com/microsoft/qlib/blob/main/qlib/backtest/exchange.py)
- A 股日内涨跌幅以前收盘价为基准：一般 ±10%，ST 股 ±5%，部分 ETF ±20%，新股上市首日不设限（来源为港股通券商说明） — [FSMOne](https://support.fsmone.com.my/hc/en-us/sections/9935583077391-6-Trading-in-different-markets)

**数据质量 / 幸存者偏差**
- Qlib README 自己提示：官方 A 股/美股数据来自 Yahoo Finance，"可能不完美"，建议有高质量数据的用户自备。由于数据安全政策，官方数据集已暂时停止提供，改为推荐社区数据源 chenditc/investment_data — [Qlib README](https://github.com/microsoft/qlib/blob/main/README.md)

**机构公开文字**
- AQR 相关：见上面的 Jensen-Kelly-Pedersen 一条。
- Man Group / Man AHL、Two Sigma：本轮搜索没有找到它们专门谈研究纪律的公开文章，见 Gaps。

### Inferences
- 个人系统应建立一张"试验登记表"，每次跑参数或换因子都记一行，这是计算 DSR / PBO 的前提；不记就无法知道自己试了多少次。
- 合理的晋级门槛可以是：t > 3（或 DSR 显著）+ CPCV 下 PBO 较低 + 样本外收益打 7 折甚至 5 折后仍然覆盖成本。这一折扣来自 McLean-Pontiff 的 26%/58%。
- Qlib 默认 `limit_threshold=None`、`impact_cost=0`，直接跑 A 股回测会高估收益；必须显式设置涨跌停（例如 0.095 或表达式）和滑点。默认 close_cost 比 open_cost 高，是为了体现卖出端的印花税。
- 前视偏差、幸存者偏差、点时（PIT）财务数据：从框架层面看，Qlib 的数据层和 Lean/zipline 的 bundle 都要求数据本身包含已退市股票、财报公告日。框架并不能自动解决这些问题，数据源才是关键。

### Gaps
- SSRN 原文（PBO、DSR、Lopez-Lira）抓取返回 403，DSR 公式细节没有核对原文。
- 没找到 Man AHL、Two Sigma 关于研究纪律的一手公开文章；paper trading（模拟盘）到实盘的过渡标准也没找到权威来源。
- 没有找到 A 股点时财务数据（如公告日对齐）权威说明的一手来源；印花税现行费率（2023-08 起减半）本轮未取得来源，需要另行核实。

## 问题 2：开源框架现状对比（截至 2026-10-30）

### Takeaway
A 股研究首选 Qlib（ML 因子流水线、Alpha158，维护活跃），A 股实盘对接首选 vn.py（4.x 已内置吸收 Alpha158 的 vnpy.alpha 模块）；美股和快速参数扫描用 vectorbt（开源版）或 Lean。backtrader 已停更约两年，新项目不建议再用。RQAlpha 能用，但许可证仅限非商业用途。

### Cited Findings（统计数据来自 GitHub API `api.github.com/repos/<repo>` 和 PyPI JSON API，2026-10-30 抓取）

| 框架 | Stars | 最近推送 | 最新版本（日期） | Python 要求 | 许可 | 来源 |
|---|---|---|---|---|---|---|
| Microsoft Qlib | 49,825 | 2026-10-30 | GitHub v0.9.8（2026-10-08）；PyPI pyqlib 0.9.7（2025-08-15） | >=3.8，classifiers 列到 3.12 | MIT | [GitHub](https://github.com/microsoft/qlib) / [PyPI](https://pypi.org/project/pyqlib/) |
| vn.py (VeighNa) | 46,150 | 2026-10-27 | 4.5.0（2026-10-06） | >=3.10（推荐 3.13） | MIT | [GitHub](https://github.com/vnpy/vnpy) / [PyPI](https://pypi.org/project/vnpy/) |
| nautilus_trader | 31,053 | 2026-10-30 | 1.231.0（2026-08-02） | >=3.12,<3.15 | LGPL-3.0 | [GitHub](https://github.com/nautechsystems/nautilus_trader) / [PyPI](https://pypi.org/project/nautilus_trader/) |
| backtrader | 23,617 | **2024-08-19** | PyPI 1.9.78.123（**2023-04-19**） | 未声明 | GPL-3.0 | [GitHub](https://github.com/mementum/backtrader) / [PyPI](https://pypi.org/project/backtrader/) |
| QuantConnect Lean | 22,300 | 2026-10-30 | 引擎不走 GitHub Release；lean CLI 1.0.233（2026-10-27） | CLI >=3.9 | Apache-2.0 | [GitHub](https://github.com/QuantConnect/Lean) / [PyPI](https://pypi.org/project/lean/) |
| vectorbt（开源版） | 9,590 | 2026-10-28 | 1.2.0（2026-10-19） | >=3.11,<3.15 | "Fair Code"（非 OSI 标准许可） | [GitHub](https://github.com/polakowo/vectorbt) / [PyPI](https://pypi.org/project/vectorbt/) |
| Backtesting.py | 9,163 | 2026-08-05 | 0.6.6（2026-07-22） | >=3.9 | AGPL-3.0 | [GitHub](https://github.com/kernc/backtesting.py) / [PyPI](https://pypi.org/project/backtesting/) |
| RQAlpha（米筐） | 6,846 | 2026-10-28 | 6.5.0（2026-10-28） | >=3.8 | 非商业使用 | [GitHub](https://github.com/ricequant/rqalpha) / [PyPI](https://pypi.org/project/rqalpha/) |
| bt | 3,012 | 2026-10-25 | 1.4.1（2026-10-10） | >=3.9 | MIT | [GitHub](https://github.com/pmorissette/bt) / [PyPI](https://pypi.org/project/bt/) |
| zipline-reloaded | 1,994 | 2026-10-26 | 3.2.1（2026-10-25） | >=3.11,<3.15 | Apache-2.0 | [GitHub](https://github.com/stefan-jansen/zipline-reloaded) / [PyPI](https://pypi.org/project/zipline-reloaded/) |

**各框架要点**
- **Qlib**：README 置顶推广 RD-Agent，这是一个基于 LLM 的自动因子挖掘与模型优化工具，2024-08-08 发布。官方数据集暂停提供，推荐社区数据源；Yahoo 数据"可能不完美" — [Qlib README](https://github.com/microsoft/qlib/blob/main/README.md)
- **Qlib 的 A 股撮合**：提供 `limit_threshold`（浮点数或买/卖表达式）、`trade_unit=100`、`volume_threshold`、开平仓费率、最低 5 元佣金、冲击成本等参数 — [exchange.py](https://github.com/microsoft/qlib/blob/main/qlib/backtest/exchange.py)
- **vn.py 4.x**：
  - vnpy.alpha 模块包含 dataset（含从 Qlib 移植的 Alpha 158）、model（Lasso / LightGBM / MLP）、strategy（截面多标的与单标的时序）、lab（数据→训练→信号→回测工作流）。
  - A 股交易网关有中泰 XTP、华鑫奇点 TORA；美股通过 Interactive Brokers 网关；数据服务可接迅投研。
  - 回测有 cta_backtester（GUI）和 portfolio_strategy（多合约）两个模块。
  - 系统支持 Windows 11+ 和 Ubuntu 22.04+。
  — [vnpy GitHub](https://github.com/vnpy/vnpy)
- **RQAlpha**：README 明确写"仅限非商业使用"，商用需联系米筐。数据通过 RQData（rqdatac，A 股从 2005 年起，收费服务）；`sys_transaction_cost` mod 负责股票和期货的税费计算。README 没有提到美股 — [RQAlpha GitHub](https://github.com/ricequant/rqalpha)
- **vectorbt**：开源社区版。作者的主要精力放在付费的 VectorBT PRO 上，PRO 增加了并行、更多数据集成、组合优化、限价单、杠杆等 100 多项功能 — [vectorbt README](https://github.com/polakowo/vectorbt)；论坛有人指出，它是单人项目、作者主攻 Pro 版是一个风险点 — [Wilmott 论坛](https://forum.wilmott.com/viewtopic.php?p=876767)。PRO 定价本轮没查到。
- **backtrader**：二手评测称它是社区维护、更新很少，有 backtrader_next 等活跃 fork；与上面的 API 数据（最后 PyPI 发布 2023-04）一致 — [ForexTester](https://forextester.com/blog/backtrader-alternatives/)
- **聚宽 JoinQuant**：在线平台，自称近 50 万个人和机构注册用户。本地数据 SDK jqdatasdk 与官网在线回测环境（jqdata）是两套体系，API 略有不同 — [jqdatasdk GitHub](https://github.com/JoinQuant/jqdatasdk)；[PyPI](https://pypi.org/project/jqdatasdk/1.9.3/)。没有找到 2025–2026 停服或收费变动的可靠信息。

### Inferences
- **A 股 T+1、涨跌停支持**：
  - Qlib 显式支持涨跌停和 100 股一手（已从源码确认），但需要手动开启。
  - vn.py 和 RQAlpha 面向国内市场设计，RQAlpha 有 A 股税费 mod。T+1 / 涨跌停的具体实现，本轮没能从 README 确认。
  - vectorbt、backtrader、Backtesting.py、bt、zipline、nautilus、Lean 都是通用或美股取向，A 股规则需要自己写（例如在信号层屏蔽当日买入后当日卖出、屏蔽涨停买入和跌停卖出）。
- **美股**：Lean（自带 QuantConnect 数据生态）、zipline-reloaded（Stefan Jansen 维护，配套《ML for Algorithmic Trading》）、nautilus（事件驱动、Rust 内核、偏实盘）都合适。vectorbt 适合快速做参数网格扫描，但要警惕扫描本身就是"多次试验"，需要配合 DSR。
- **学习曲线（主观判断）**：从低到高大致是 Backtesting.py / bt < vectorbt < backtrader < Qlib ≈ zipline < vn.py < Lean（C# 内核 + Docker CLI）≈ nautilus。
- **许可注意**：Backtesting.py 是 AGPL；RQAlpha 不可商用；vectorbt 是 Fair Code；nautilus 是 LGPL。个人研究不受影响，以后若做成对外服务需要复查。
- **Python 版本**：nautilus 要求 >=3.12，vectorbt / zipline 要求 >=3.11，Qlib 官方 classifiers 只列到 3.12。统一用 Python 3.12 能同时满足上述全部框架。这是推断，未在每个框架上实际安装验证。

### Gaps
- vectorbt PRO 的价格和许可细节、聚宽当前收费政策，均未取得一手来源。
- 各框架 T+1 实现细节（vn.py、RQAlpha）没能从文档直接确认。
- Lean 引擎本体的 Python 版本（Python.NET 绑定）没有核实。

## 问题 3：LLM / AI 用于个人量化的可信证据与局限

### Takeaway
目前最有代表性的证据是 Lopez-Lira & Tang：用 GPT 给新闻标题打情绪分，能预测次日收益，越大的模型效果越好；但最新版（v6，2025-10）承认随着 LLM 普及，策略收益在下降。另一项研究发现 LLM 回测存在严重的前视偏差，样本外优势大幅缩水。个人使用时，必须用模型知识截止日之后的数据做样本外检验。

### Cited Findings
- Lopez-Lira & Tang（佛罗里达大学），"Can ChatGPT Forecast Stock Price Movements? Return Predictability and Large Language Models"：
  - 让 ChatGPT 判断标题对个股是利好、利空还是中性，这一标签能预测次日收益；ChatGPT-4 多空策略夏普最高；GPT-1、GPT-2、BERT 等小模型预测效果差。
  - 可预测性集中在小盘股和坏消息上，作者归因于投资者反应不足和套利限制。
  - 最新版 v6（2025-10）称：随着 LLM 采用率上升，策略收益下降，与市场效率提高一致，但均衡下仍残留部分可预测性。
  — [arXiv 2304.07619v6](https://arxiv.org/pdf/2304.07619v6)；[v5 HTML](https://arxiv.org/html/2304.07619v5)
- 早期版本强调"AI 能力存在一个盈利所需的临界门槛"，"随采用率衰减"的结论是后续版本才加入的 — [arXiv v1](https://arxiv.org/abs/2304.07619v1)
- Glasserman & Lin（arXiv 2309.17322，2023）：
  - 设计：用 GPT-3.5 对新闻标题做情绪分析并构建多空策略，比较原始标题与匿名化标题（替换掉公司名）的结果。
  - 样本内：匿名化标题反而更好。作者称之为"分心效应"，即模型对公司的一般知识反而有害，大公司更明显。
  - 样本外：匿名化的优势在整体上不再显著，说明样本内差距大部分来自模型对未来事件的知识，也就是前视偏差。
  — [arXiv](https://arxiv.org/abs/2309.17322)
- 2026 年出现了专门的基准 Look-Ahead-Bench，用来衡量"点时 LLM"在金融任务上的前视偏差 — [arXiv 2601.13770](https://arxiv.org/pdf/2601.13770)
- Qlib 生态的 RD-Agent 用 LLM 自动挖因子、改模型 — [Qlib README](https://github.com/microsoft/qlib/blob/main/README.md)

### Inferences
- 用 LLM 回测历史新闻时，训练语料很可能已经包含事后结果。可信检验只能用模型知识截止日之后的数据，或者把公司名匿名化。
- LLM 自动挖因子（RD-Agent 一类）本质上是在大量增加"试验次数"，更需要配合 DSR / PBO 和 t > 3 的门槛。
- 已发表的 LLM 情绪 alpha 自身就在衰减（Lopez-Lira v6），个人很难靠"标题情绪"这种公开方法长期获利。更现实的用途是信息整理、事件标注、作为特征之一放进 ML 模型。

### Gaps
- 没找到 Lopez-Lira 结论的独立复现；A 股中文新闻上 LLM 情绪因子的可靠学术证据本轮没有检索到。
- 衰减幅度的具体数字（收益下降多少）没有从原文表格中取得。

## 问题 4：个人开发者的推荐架构

### Takeaway
采用"数据层 → 因子层 → 模型/信号层 → 回测/撮合层 → 风险报告层 → 信号输出"的分层结构。A 股用 Qlib 做研究主干，vn.py 做实盘对接；美股用 vectorbt 或 zipline-reloaded 做研究，Lean / IB 做执行。所有晋级决策走"试验登记 + DSR / PBO + 样本外 + 模拟盘"的闸门。这些组件都有来源支撑，但整体组合是本人推断，并非某个来源直接推荐。

### Cited Findings
- Qlib 提供从数据、特征（Alpha158）、模型、回测到分析的完整 ML 流水线，并支持自定义 CSV 数据转换为 Qlib 格式 — [Qlib README](https://github.com/microsoft/qlib/blob/main/README.md)
- vnpy.alpha 的 lab 模块已经把"数据→训练→信号→回测"的流程模板化，并且可以接 XTP / TORA（A 股）和 IB（美股）实盘网关 — [vnpy GitHub](https://github.com/vnpy/vnpy)
- Qlib 的 Exchange 可以配置涨跌停、一手 100 股、成交量约束、费率和冲击成本 — [exchange.py](https://github.com/microsoft/qlib/blob/main/qlib/backtest/exchange.py)
- DSR / PBO / CPCV 分别对应风险报告层应输出的过拟合指标 — [DSR SSRN](https://papers.ssrn.com/abstract=2460551)；[PBO Risk.net](https://www.risk.net/journal-of-computational-finance/2471206/the-probability-of-backtest-overfitting)；[Purged CV](https://en.wikipedia.org/wiki/Purged_cross-validation)

### Inferences（推荐方案，属推断）
1. **数据层**：Parquet / DuckDB 本地仓库。日线行情必须包含已退市股票；财务数据按公告日对齐（点时）。A 股可以用社区数据 chenditc/investment_data 起步，美股需要另找带退市股票的数据源。统一保存复权因子、停牌标记、涨跌停价。
2. **因子层**：Qlib 表达式引擎 / Alpha158 作为基线，自定义因子写成纯函数，并带 `available_at` 时间戳。
3. **模型/信号层**：LightGBM 基线，用 purged k-fold + embargo（不少于 2 倍持有期）调参，外层用滚动 walk-forward。
4. **回测层**：
   - A 股：Qlib backtest，显式设置 `limit_threshold`、`trade_unit=100`、`impact_cost`。T+1 需要自己确认或实现。
   - 美股：vectorbt 做快速扫描，再用事件驱动框架（zipline-reloaded / nautilus / Lean）复核。
5. **风险报告层**：每个候选策略输出：
   - 夏普、PSR / DSR（输入登记表里的试验次数）
   - CPCV 下的 PBO
   - 因子 t 值（门槛 3）
   - 换手率与成本敏感性（成本 ×2 后是否仍然盈利）
   - 分年度、分市值档的绩效
   - 样本外打 26%–58% 折扣后的预期
6. **信号输出 / 执行**：先跑至少数月模拟盘，对比回测和模拟盘的成交价与滑点偏差，再接 vn.py（A 股）或 IB（美股）小资金实盘。
7. **LLM 模块**：只作为特征或事件标注，回测仅使用模型知识截止日之后的数据，并对比匿名化标题的效果。

### Gaps
- 模拟盘时长、实盘资金放大规则等没有找到权威来源，第 6 条中的"数月"是经验推断。
- 美股带退市股票的免费或低价数据源本轮没有调研（可能由其他调研员负责）。
