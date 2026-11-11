# quant-allocation-research

[![CI](https://github.com/kennywu411-dev/quant-allocation-research/actions/workflows/ci.yml/badge.svg)](https://github.com/kennywu411-dev/quant-allocation-research/actions/workflows/ci.yml)

个人跨市场（A股 + 美股）ETF 配置研究系统，用 Python 自建：数据清洗、回测引擎、预登记选参、样本外检验、A股单因子检验，以及影子盘、模拟盘的执行偏差监控。

> **声明**：这是个人研究记录，不是投资建议。所有收益和回撤都来自历史回测，不代表未来。作者不是持牌金融顾问。

## 主要结论

| 内容 | 结果 | 出处 |
|---|---|---|
| 回测引擎校准 | 和开源库 bt 交叉核对，年化与最大回撤差均为 0.00 个百分点 | `reports/P2-回测校准-2026-10-30.md` |
| 核心配置（美股 60% 标普500，A股 30% 沪深300 + 红利，其余债券和黄金，10 个月均线转国债；2007-06 至 2026-10，人民币计） | 年化 5.9%，样本内（至 2019）6.0%，样本外（2020 起）5.8%；三种调仓日中最差的最大回撤 -14.2% | `reports/P5-最终方案-2026-10-31.md` |
| 5 个因子 ETF 卫星候选 | 全部否决。例如红利低波的 alpha t = 3.12，但按试验次数折扣后，通缩夏普只有 0.85（门槛 0.95） | `reports/P4-卫星-2026-11-04.md` |
| 幸存者偏差估计 | 用今天的成分股回测动量个股组合，比含退市股的 French 组合每年高 25.0 个百分点 | `reports/动量个股检验-2026-11-04.md` |
| A股单因子检验（7 个因子，今天的沪深300 成分股，2010–2026） | 按运行前固定的门槛（t ≥ 3 且样本外同号）全部不显著，最高为 12-1 动量（t = 1.88） | `reports/因子检验-2026-11-10.md` |
| 大模型读公告（Claude Haiku 结构化标注沪深300 成分股 27.4 万条公告标题，2020–2026） | 判定标准在标注前提交。主假设（模型知识截止后的干净样本、持有 5 天、实质性利好减利空）未通过：-0.35%，t = -0.96；用两个知识截止日不同的模型在同一时段对照，前视增益不显著（t = 0.93）。总花费 7.65 美元 | `reports/公告因子-2026-11-11.md` |

## 趋势过滤的代价（基准对比）

口径与 P5 报告一致（两账户合并、人民币计、2007-06 至 2026-10，最大回撤取三种调仓日中最差的）。脚本 `quant/research/benchmarks.py`，结果 `research/p5_benchmarks.json`。

| 指标 | 核心配置（加 10 个月均线） | 同权重、不加均线 | 纯股票（SPY / 沪深300） |
|---|---:|---:|---:|
| 全期年化 | 5.9% | 7.3% | 7.3% |
| 样本外年化（2020 起） | 5.7% | 9.3% | 10.5% |
| 最差最大回撤 | -14.2% | -32.0% | -61.0% |
| 年化波动 | 8.3% | 9.6% | 16.7% |
| 夏普 | 0.39 | 0.49 | 0.33 |
| 卡玛 | 0.41 | 0.23 | 0.12 |

趋势过滤把最大回撤从 -32.0% 降到 -14.2%（主要是 2008 年：2.8% 对 -19.0%），代价是年化 5.9% 对 7.3%、夏普 0.39 对 0.49；2022 年股债同跌时反而更差（-10.1% 对 -4.0%）。它是回撤保险，不是收益来源。

## 防过拟合的做法

- **试验登记**：每次试验追加一行到 `research/trials.csv`，带运行编号（`quant/research/registry.py`）。
- **样本切分**：2019-12-31 以前是样本内，用于排名；2020 年以后是样本外，只检验，不参与选择。
- **门槛在运行前写进代码**（`quant/research/gates.py`）：样本外为正且不低于样本内一半、成本翻倍仍盈利、换调仓日的年化差 ≤ 2 个百分点、去掉最好的一年仍盈利。
- **统计检验**：Newey-West 调整的 alpha t 值、通缩夏普比率（`quant/research/stats.py`）；风控规则用平稳分块自助法比较（`quant/research/riskrule.py`）。

## 目录

```
quant/
  data/        行情下载与缓存（AKShare、yfinance 等免费源），ETF 份额拆分修正
  backtest/    月度调仓回测引擎（涨跌停、停牌、整手、成本、汇率）、与 bt 交叉核对
  research/    P3 核心配置、P4 卫星、P5 组合与风控、激进版研究、统计检验
  factors/     A股单因子检验（数据、因子、IC / 分组 / 成本）
  llm_events/  大模型读公告：巨潮公告下载、结构化标注（Batch API、缓存、预算上限）、事件研究与月度情绪因子
  live/        月度调仓单、份额净值账本、影子盘、模拟盘（只允许 SIMULATE）、偏差报告
  portfolio/   持仓体检与过渡方案
reports/       各阶段研究报告
research/      试验登记表与结果数据
tests/         单元测试
```

## 运行

```bash
python3.12 -m venv .venv && .venv/bin/pip install pandas numpy pyarrow yfinance akshare baostock matplotlib bt moomoo-api anthropic pytest
.venv/bin/pytest -q
```

A股单因子检验（单线程下载，约 70 分钟）：

```bash
PYTHONPATH=. .venv/bin/python -m quant.factors.data_current
PYTHONPATH=. .venv/bin/python -m quant.factors.run --source current
```

大模型读公告（需要 `ANTHROPIC_API_KEY`；下载约 2 小时，标注用 Batch API）：

```bash
PYTHONPATH=. .venv/bin/python -m quant.llm_events.data
PYTHONPATH=. .venv/bin/python -m quant.llm_events.label --model claude-haiku-5-5
PYTHONPATH=. .venv/bin/python -m quant.llm_events.label --model claude-haiku-4-5 --start 2025-08-01
PYTHONPATH=. .venv/bin/python -m quant.llm_events.label --review 200
PYTHONPATH=. .venv/bin/python -m quant.llm_events.run
```

## 不在仓库里的输入

- `config/holdings.csv`：真实持仓，不公开。格式见 `config/holdings.example.csv`。持仓体检、过渡方案和实盘对照都要用它。
- 两个账户合并回测用的账户市值比例不公开：`trials.csv` 和 `research/*.json` 里已删掉这一列，报告里也删掉了具体比例。合并类的命令需要自己用 `--w-us` 传入。
- moomoo 模拟账户号：用环境变量 `MOOMOO_PAPER_ACC_ID` 提供，或写进 `config/moomoo_paper_acc_id.txt`（已 gitignore）。
- `live/`：真实调仓单、影子盘和模拟盘记录，不公开。

## 许可证

MIT，见 `LICENSE`。
