# 数据源与券商交易接口调研（银河证券 A 股 + moomoo AU 美股）

> 调研日期：2026-10-30。本轮约 18 次检索/抓取。标注规则：【官方】= 券商、交易所或数据商官网；【二手】= 论坛、客户经理问答、比价站或博客；【未核实】= 找不到可靠来源。

## 1. 银河证券：程序化/量化终端（QMT/miniQMT、PTrade、玉衡）、门槛、佣金、2025 程序化交易新规

### Takeaway
多方二手来源都说银河证券向零售客户开放 QMT/miniQMT（有的也说开放 PTrade），但没找到银河官网的开通页面或公告。资金门槛众说纷纭：10 万元（miniQMT/基础版）、50 万元（全功能版）、300 万元（极速柜台），也有"无门槛"的说法，必须向客户经理或 App"业务办理"书面确认。2025-07-07 起施行的交易所《程序化交易管理实施细则》要求程序化交易先报告再交易；高频认定标准为单账户每秒申报加撤单 ≥300 笔，或全日 ≥20000 笔，个人低频策略一般够不到高频线。

### Cited Findings
- 【二手】银河证券支持 QMT 和 MiniQMT。基础版 QMT 免费开通的条件是近 20 个交易日日均资产 ≥10 万元 — [叩富网问答](https://licai.cofool.com/ask/qa_5340255.html)
- 【二手】银河 QMT 分三档：MiniQMT 10 万起、全功能版 50 万起、极速柜台 300 万起。另一条回答的 MiniQMT 条件是：近 20 日日均金融资产 ≥10 万（"部分渠道可谈至 5 万"）、风险测评 C4 及以上、6 个月 A 股交易经验 — [叩富网 银河量化门槛](https://licai.cofool.com/ask/vipqa_7311004_43391200.html)；[叩富网 qa_3245211](https://licai.cofool.com/ask/qa_3245211.html)
- 【二手，相互矛盾】有回答说"50 万资金即可免费开通"，也有回答说银河"提供了 QMT 和 PTrade 量化软件，无资金要求且免费使用" — [叩富网 qa_3056387](https://licai.cofool.com/ask/qa_3056387.html)；[叩富网 qa_4148624](https://licai.cofool.com/ask/qa_4148624.html)
- 【二手】开通途径：在银河 App 或交易软件的"业务办理"里找到 QMT 权限申请入口，或联系客户经理。开通时要签量化交易风险揭示书或协议 — [叩富网 qa_3484116](https://licai.cofool.com/ask/qa_3484116.html)；[叩富网 qa_6834443](https://licai.cofool.com/ask/qa_6834443.html)
- 【二手，非官方站】miniqmt.com 是第三方引流站，不是银河或迅投官网，引导用户加微信开户 — [miniqmt.com QA](https://miniqmt.com/pages/qanda.html)
- 【官方】沪深北交易所《程序化交易管理实施细则》于 2025-04-03 发布，2025-07-07 起施行。细则实行"先报告后交易"，并对高频交易设差异化收费（流量费、撤单费） — [上交所答记者问](https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20250403_10776805.shtml)；[新华网](https://www.news.cn/money/20250407/3142c6f5fd1d4b1ebd9eb91910befc5e/c.html)
- 【官方】高频交易认定标准：单账户每秒申报、撤单合计 ≥300 笔，或单日 ≥20000 笔。交易所重点监控瞬时申报速率异常、频繁瞬时撤单、拉抬打压、短时大额成交 — [上交所答记者问](https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20250403_10776805.shtml)；[同花顺新闻](https://news.10jqka.com.cn/20250407/c667241566.shtml)
- 【官方，2024 征求意见稿】深交所程序化交易细则征求意见稿全文（PDF）— [深交所 PDF](https://docs.static.szse.cn/www/disclosure/notice/general/W020240607673406988136.pdf)

### Inferences
- 个人用 miniQMT 跑日频或分钟级低频策略，按细则仍属"程序化交易"，需要经券商向交易所报告账户、资金、策略类型、下单软件等信息。这一步通常在开通 QMT 时由券商代办，报告字段以券商表单为准。只要远离每秒 300 笔、每日 20000 笔的阈值，就不会被认定为高频，也不会承担额外费用。
- 门槛信息全部来自客户经理引流帖，这类帖子有压低门槛的动机，可信度低。10 万元是出现频率最高的说法，可作为初步预期，最终以营业部书面答复为准。
- miniQMT 的工作方式是：本地 Windows 客户端运行，Python 通过 xtquant 库连接。实际意味着要有一台常开的 Windows 机器或 Windows VPS，macOS 不能原生运行（此条为背景知识，本轮未取到来源）。

### Gaps
- 没找到银河证券官网（chinastock.com.cn）上关于 QMT、PTrade 或"玉衡"的官方产品页、开通条件和费用公告。"玉衡"是否是面向零售的量化终端，还是银河内部的核心交易系统或极速柜台，无法核实。
- 银河零售佣金：本轮没找到可引用来源。行业常见的线上开户可谈价约万 1.5 至万 2.5（含规费与否各家口径不同），属【未核实】背景知识，需向客户经理索取书面费率。另外，QMT 账户有时要求不低于某个佣金下限，也未核实。
- 程序化交易报告的具体字段，以及个人投资者在券商端的报告流程，没取到官方原文。建议看沪深交易所官网细则全文和银河 App 的提示。
- 境外居住的个人能否远程开通 QMT，以及登录 IP 是否受限，未核实。

## 2. moomoo AU：OpenAPI（Futu OpenD）能否交易美股、模拟盘、行情权限、限频、SDK、佣金与换汇费

### Takeaway
能交易。moomoo 官方 OpenAPI 帮助页的交易能力表显示，Moomoo AU 账户可通过 OpenAPI 实盘交易美股和 ETF（NYSE、NYSE-American、Nasdaq），也可交易港股；美股期权、期货和 A 股通实盘不支持。模拟盘支持美股（含期权）。通过 API 交易不额外收费。美股交易佣金为每单 US$0.99（不含转嫁费），换汇点差约 0.5%–0.55%（各来源不一致）。行情订阅额度按资产分档，部分接口有单独的频率限制。

### Cited Findings
- 【官方】OpenAPI 交易能力表中 Moomoo AU 一列：美股股票和 ETF 实盘 √；美股期权 ×；美股期货 ×；港股股票、ETF、窝轮、牛熊证 √；港股期权和期货 ×；A 股通 ×。模拟盘列中，美股股票、ETF 和期权均为 √。"通过 Moomoo API 交易不额外收费"（表格列映射是从扁平化文本推断的，需在 App 中验证）— [moomoo AU 帮助中心 OpenAPI](https://www.moomoo.com/au/support/topic3_436)
- 【官方】OpenAPI 文档主页（v10.12）称"交易接口同时用于实盘与模拟交易"。SDK 支持 Python、Java、C#、C++、JavaScript 和 proto 协议；OpenD 网关可在本地或云端运行，支持 Windows、macOS、CentOS、Ubuntu — [OpenAPI 文档 intro](https://openapi.moomoo.com/moomoo-api-doc/en/intro/intro.html)
- 【官方，有冲突】同一文档主页的扁平化表格中，"澳洲市场（股票、ETF）"一行全是 ×，可能意味着 OpenAPI 不支持 ASX 交易（解析不可靠）。开发者总览页又把 AU 列为股票和 ETF 市场 — [OpenAPI 文档 intro](https://openapi.moomoo.com/moomoo-api-doc/en/intro/intro.html)；[open.moomoo.com 总览](https://open.moomoo.com/api/overview/)
- 【官方】期货实盘目前只开放给 Moomoo SG 和 FUTU HK 账户，Moomoo US 和 Moomoo AU 不支持 — [moomoo 帮助中心（检索摘要）](https://www.moomoo.com/us/support/topic3_436)
- 【官方】行情权限：美股 LV3（Nasdaq Basic、TotalView、NYSE ArcaBook）在推广期内免费，深度行情需先完成非专业用户（Non-pro）评估。美股期权 LV1 对总资产 >0 或持有美股仓位的客户免费，其他客户需购买 OPRA 实时行情。大陆认证用户与全球用户按 OpenD 登录 IP 区分。页面没有给出 AU 专属价格，推广期起止也没有日期 — [OpenAPI 权限页](https://openapi.moomoo.com/moomoo-api-doc/en/intro/authority.html)
- 【官方】订阅额度（股票 / 历史 K 线 / 期权 / 期权 K 线）：总资产 <1 万港币为 100/100/20/20；≥1 万港币为 300/300/60/60；资产 >50 万港币、月成交 >200 笔或月成交额 >200 万港币为 1000/1000/200/200；资产 >500 万港币、月成交 >2000 笔或月成交额 >2000 万港币为 2000/2000/400/400。入金后 2 小时内生效。各接口另有单独限频，例如"获取快照"为每 30 秒 60 次 — [OpenAPI 权限页](https://openapi.moomoo.com/moomoo-api-doc/en/intro/authority.html)
- 【官方】moomoo AU 美股佣金每单 US$0.99，另有转嫁费和换汇成本。ASX 佣金为 A$3 与 0.03% 取高者（含平台费） — [moomoo AU 美股页](https://moomoo.com/au/invest/us-stock)；[moomoo AU pricing](https://moomoo.com/au/pricing)；[moomoo AU 费用表](https://moomoo.com/au/support/topic6_373)
- 【官方 vs 二手，有冲突】换汇费：moomoo 对比 Stake 的文章写 0.55%，对比 CommSec 的文章写 AUD/USD 0.5%，Wise 测算约 0.5% — [moomoo vs Stake](https://www.moomoo.com/au/learn/moomoo-vs-stake)；[moomoo vs CommSec](https://www.moomoo.com/au/learn/moomoo-vs-commsec)；[Wise 评测](https://wise.com/au/blog/moomoo-review)
- 【二手】Finder 列出的 30 天 $0 佣金新户优惠已于 2026-05-31 到期 — [Finder moomoo review](https://www.finder.com.au/moomoo-review)

### Inferences
- moomoo AU 用 OpenAPI 做美股现货和 ETF 的自动化交易是可行的，模拟盘可以先跑通，也可以先拿港股模拟盘做功能测试。如果策略需要美股期权，AU 账户不支持，只能手动或换券商。
- 小资金账户（<1 万港币，约 A$2,000）只有 100 个实时订阅和 100 个历史 K 线额度。"历史 K 线额度"是按 30 天内去重的股票数计算（背景知识，未核实），全市场回测不能靠 moomoo 拉历史数据，要另找数据源。
- 小额频繁交易时，US$0.99 每单加 0.5% 左右的双边换汇成本，后者是主要摩擦。建议一次性换汇后长期持有美元现金。

### Gaps
- 下单接口的具体限频（如 place_order 每 30 秒次数）本轮未取到官方页面。旧文档写的是每 30 秒最多 15 次，属【未核实】。
- Python SDK 包名与现状：Futu 品牌为 `futu-api`，moomoo 品牌为 `moomoo-api`（PyPI 包名为背景知识，未取到 PyPI 或 GitHub 页面核实）。2026 年的最新版本号也未核实。
- AU 用户美股 LV1/LV2 行情的具体收费，以及推广期截止日期，未找到。
- AU 账户的 OpenAPI 能否交易 ASX 股票：文档内部表述不一致，需要实测或问客服。

## 3. A 股数据：AKShare、Tushare Pro、BaoStock、JQData、Choice/iFinD、qlib；PIT 财务、复权、退市股覆盖

### Takeaway
免费层：AKShare 靠爬取网页，覆盖广，但会随源站改版而失效，频繁请求可能被封 IP；BaoStock 免费、有限频，支持日/周/月/分钟线和三种复权方式。Tushare Pro 是积分门槛制（门槛积分不消耗），日线需 120 分，大部分股票、财务和复权数据需 2000 分，期权和基金持仓需 5000 分；分钟数据另行付费。本轮没有拿到可靠来源来确认退市股覆盖和 PIT（按公告日对齐）财务数据。

### Cited Findings
- 【官方】Tushare 权限表：120 分可用日线、新股、LPR、Shibor/LIBOR/HIBOR；2000 分可用大部分股票、财务、基金、期货、期权、债券、外汇、指数、港股数据，以及周/月线、复权行情 pro_bar 和每日指标；3000 分可用限售解禁；4000 分可用指数每日指标；5000 分可用基金持仓、基金复权因子、期权日线。门槛"并不消耗积分"，积分越高每分钟调用次数越多，但页面没有给出具体数字。分钟数据和特色数据单独处理，港股分钟数据标注"2000 元" — [Tushare 权限说明](https://tushare.pro/document/1?doc_id=108)
- 【二手】有教程称分钟数据需要捐助 1000 元才能解锁，财务报表需要 2000 积分 — [掘金教程](https://juejin.cn/post/7646404763680407615)
- 【二手】2026 年 2 月新注册用户反馈调用日线接口报"无权限" — [Tushare GitHub issue #1844](https://github.com/waditu/tushare/issues/1844)
- 【二手】2026 年选型横评：AkShare 是爬虫式接口，易受源站改版影响，频繁请求可能被封 IP — [腾讯云开发者文章](https://cloud.tencent.com/developer/article/2711472)
- 【二手】BaoStock API 有调用频率限制（下载器项目内置了休眠），支持日/周/月/分钟 K 线和 3 种复权类型 — [Gitee baostock 镜像](https://gitee.com/james112496/baostock)
- 【二手】有开源项目选择 A 股用 BaoStock（项目自述"数据质量高，财务数据完整"），港美股用 AkShare — [stockreport-mcp 源码](https://glama.ai/mcp/servers/@jamesdingAI/stockreport-mcp/blob/b3baeb1054a2153ef1235e29d571e7c11abc65a4/src/hybrid_data_source.py)

### Inferences
- 个人做 A 股日频研究，比较务实的组合是：BaoStock 打底（含复权），Tushare 2000 分档补财务和每日指标，AKShare 补零散数据。Tushare 积分获取办法见其 doc_id=13，本轮未取到，金额待核实。
- 做无幸存者偏差的回测，要拿历史全部股票列表（含已退市）和每个交易日的成分。拿到之前，应先用几只已知退市股（如退市的 *ST 股）实测各数据源能否返回完整历史。

### Gaps
- Tushare 积分获取方式和捐助金额（doc_id=13）未取到。2000 分档大约对应多少元，属【未核实】。
- JQData（聚宽）、东方财富 Choice、同花顺 iFinD、Wind 的价格本轮都没取到来源。Choice、iFinD、Wind 一般是年费数千至数万元的终端产品，属【未核实】背景知识。
- 各源对已退市股票的覆盖、PIT 财务（按公告日对齐、保留修订前数值）是否可得，都没找到可靠资料。
- qlib 自带的 A 股数据（cn_data）：社区版的官方数据下载曾因数据许可暂停，社区改用第三方打包数据，属【未核实】，本轮未取到 GitHub 来源。

## 4. 美股数据：yfinance、Alpha Vantage、Polygon（现名 Massive）、Tiingo、EODHD、Sharadar/Nasdaq Data Link、FMP、CRSP

### Takeaway
Polygon.io 已于 2025-10-30 更名为 Massive，旧 API 地址继续支持。Massive 官网目前的 Stocks Advanced 档为 $199/月（实时、20 年以上历史、财务数据，仅限个人用途），单独的 Financials & Ratios 为 $29/月。yfinance 在 2024–2025 年间反复出现 Yahoo 429 限流和接口失效，不适合作为生产数据源。要做无幸存者偏差的研究，Sharadar 的证据最强（保留退市公司），EODHD 也提供退市数据，FMP 需要自己拼。

### Cited Findings
- 【官方新闻稿】Polygon.io 自 2025-10-30 起更名为 Massive，api.polygon.io 会长期继续支持，SDK 同步更名 — [EIN Presswire](https://www.einpresswire.com/article/863823068/polygon-io-is-now-massive)；[FISD](https://fisd.net/polygon-io-is-now-massive)
- 【官方】Massive 定价页：Stocks Advanced $199/月（财务与比率、实时股票数据、20 年以上历史、websocket，仅限个人用途）；Financials & Ratios $29/月；年付省 20%；商业用途另行报价。页面没有列出限频或 flat files 细节 — [Massive pricing](https://massive.com/pricing)
- 【二手，与官方页不完全一致】比价站列出 Basic $0、Starter $29、Developer $79、Advanced $199 — [QVeris 指南](https://qveris.ai/guides/polygon-pricing-optimized/?lang=zh)；[apicostcalc](https://apicostcalc.com/blog/polygon-massive-rebrand-api-pricing.html)
- 【GitHub】yfinance 0.2.57 至 0.2.59 出现 YFRateLimitError 和 HTTP 429，换 IP 也无效（2025-04）。批量拉约 950 只股票后被 429（2024-11）。维护者解释是 Yahoo 会在短时间请求过多后临时封 IP — [issue #2422](https://github.com/ranaroussi/yfinance/issues/2422)；[issue #2128](https://github.com/ranaroussi/yfinance/issues/2128)；[discussion #2431](https://github.com/ranaroussi/yfinance/discussions/2431)
- 【二手】QuantConnect 用户反馈 yfinance 0.2.52 失效，需要升级到 0.2.54 — [QuantConnect 论坛](https://www.quantconnect.com/forum/discussion/18702)
- 【二手】EODHD 入门付费档约 $19.99/月（$199/年），基本面档 $59.99/月。功能上含退市股和代码变更数据（Tiingo 没有） — [findmymoat EODHD vs Tiingo](https://www.findmymoat.com/vs/eodhd-eod-historical-data-vs-tiingo)；[findmymoat EODHD vs FMP](https://www.findmymoat.com/vs/eodhd-vs-financial-modeling-prep-fmp)
- 【二手】FMP 免费档每日 250 次调用，入门付费档约 $19–29/月（各来源不一）。要得到含退市股的股票池需要自己拼装 — [findmymoat FMP vs Tiingo](https://www.findmymoat.com/vs/financial-modeling-prep-fmp-vs-tiingo)；[Pickuma FMP vs Sharadar](https://pickuma.com/for-dev/financial-modeling-prep-vs-sharadar-fundamental-data-api/)
- 【二手】Tiingo 个人档 $30/月（$300/年） — [findmymoat Tiingo 替代](https://www.findmymoat.com/alternatives/tiingo)
- 【二手】Sharadar 的 SF1 和 TICKERS 表保留退市公司，可构建无幸存者偏差股票池。2026 年中价格估计为"每月低几百美元"，属博客估计，未核实 — [Pickuma FMP vs Sharadar](https://pickuma.com/for-dev/financial-modeling-prep-vs-sharadar-fundamental-data-api/)

### Inferences
- 预算有限的个人可以这样分层：免费阶段用 yfinance 做原型（加缓存、限速）；严肃回测用 Sharadar（无幸存者偏差、含 PIT 基本面）或 EODHD（便宜、含退市）；需要实时或分钟数据时再考虑 Massive。如果交易只在 moomoo 执行，实时行情可以直接用 moomoo OpenAPI 的推送，不必另买。
- Massive 官网只展示了 $199 档和 $29 财务档，二手站列的 $29/$79 股票档可能已经下架或只在别处展示，下单前要再看官网。

### Gaps
- Alpha Vantage 当前价格和免费额度、Nasdaq Data Link 上 Sharadar 的官方价格、CRSP（一般需机构订阅，个人通过大学 WRDS 访问）都没取到官方来源。CRSP 可通过 UNSW 的 WRDS 访问，属【未核实】，需向 UNSW 图书馆确认。
- Tiingo 的退市股覆盖没有来源。
- Massive 各档的限频和 flat files 权限，官方页没有列出。

## 5. 税务与监管（澳洲税务居民交易 A 股与美股，高层次）

### Takeaway
在 moomoo 提交 W-8BEN 后，按澳美税收协定美股股息预扣 15%（未提交为 30%）。表格大致在签署后第三个日历年末到期，需要续签。已缴外国税可在澳洲申报外国所得税抵免（FITO），但有上限，超额部分作废、不能结转。若资本利得享受了 50% CGT 折扣，FITO 只能按计入应税收入的部分对应抵免（联邦法院支持 ATO 的口径）。澳洲税务居民需申报全球所得，包括 A 股的资本利得和股息。

### Cited Findings
- 【二手】澳美协定下，澳洲证券投资者的美股股息预扣上限为 15%，须提交 W-8BEN，否则按 30% 预扣。W-8BEN 有效期至签署后第三个日历年末 — [expattaxes.com.au](https://www.expattaxes.com.au/how-us-international-shares-taxed-australia/)；[Class 支持页](https://support.class.com.au/hc/en-au/articles/360001519715-Why-is-my-foreign-dividend-withholding-rate-30-when-standard-withholding-rate-is-only-15)
- 【二手，与通行理解冲突】有来源称未提交 W-8BEN 时卖出所得也会被预扣 30%。通常非美国居民的美股资本利得不在美国预扣，此说法存疑 — [expattaxes.com.au](https://www.expattaxes.com.au/how-us-international-shares-taxed-australia/)
- 【官方】ATO：只有外国税所对应的收入计入了澳洲应税收入，才能产生 FITO（见 ATO 关于外国来源资本利得的示例） — [ATO FITO 指南：外国税须对应应税收入](https://www.ato.gov.au/forms-and-instructions/foreign-income-tax-offset-rules-guide-2010/when-a-foreign-income-tax-offset-applies/foreign-income-tax-must-have-been-paid-on-assessable-income)
- 【二手】联邦全院法院判例：美国已缴税的资本利得在澳洲享受 CGT 折扣后只按一半计税，FITO 也只限对应部分，ATO 驳回了超额抵免 — [Public Accountant](https://publicaccountant.com.au/news/court-backs-ato-position-on-foreign-income-tax-offsets/)；[Xperion](https://xperion.com.au/court-confirms-atos-position-on-foreign-income-tax-offsets/)
- 【二手】美股预扣税不能当作 franking credit，只能用于 FITO — [Navexa](https://www.navexa.com/blog/tax-implications-for-australians-investing-in-foreign-stocks)

### Inferences
- 交易 A 股时，需要关注中国大陆对股息的预扣（个人持股期限差别化税率）和澳洲的 FITO 抵免；身份判定（澳洲税务居民还是中国税务居民）决定申报义务。本项只能高层次提示，具体需咨询注册税务师。
- 高频进出（持有不满 12 个月）不能享受 50% CGT 折扣；如果交易活动被认定为"经营交易业务"（share trader），收益按普通收入处理。此条为背景知识，未取到 ATO 原文。

### Gaps
- 没有取到 ATO 关于外国资产 CGT、12 个月折扣、share trader 与 investor 认定的官方页面原文。
- 没找到权威来源说明：中国公民以澳洲税务居民身份持有境内 A 股账户时，中澳税收协定下的股息税率，以及中国是否需要申报境外税务居民身份（CRS 相关）。
- 中国大陆是否限制境外居住者使用境内券商账户进行程序化交易，未核实。
