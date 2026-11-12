#!/bin/zsh
# 每月 1 日：因子线月度流水线（读缓存 → 算因子 → 追加观察盘记录 → 上期收益 → 监控报告 → 看板）。只记账，不下单。
# 数据源默认 tushare（由本地 Tushare 日线缓存合成周线）：本脚本不联网下载，跑之前先运行 quant.tsdata.download 更新缓存，
# 否则只会用到缓存里已有的日期。ALPHA_SOURCE=cache 可改回 baostock 周线缓存。
cd "$(dirname "$0")/.." || exit 1
mkdir -p live/logs
{ date; PYTHONPATH=. .venv/bin/python -W ignore -m quant.alpha.pipeline --source "${ALPHA_SOURCE:-tushare}" && PYTHONPATH=. .venv/bin/python -W ignore -m quant.alpha.dashboard; } >> live/logs/alpha_monthly.log 2>&1
