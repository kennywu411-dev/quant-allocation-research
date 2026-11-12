#!/bin/zsh
# 每月 1 日：因子线月度流水线（读缓存 → 算因子 → 追加观察盘记录 → 上期收益 → 监控报告 → 看板）。只记账，不下单。
# 数据源默认 cache；Tushare 数据层就绪后把 ALPHA_SOURCE 改成 tushare。
cd "$(dirname "$0")/.." || exit 1
mkdir -p live/logs
{ date; PYTHONPATH=. .venv/bin/python -W ignore -m quant.alpha.pipeline --source "${ALPHA_SOURCE:-cache}" && PYTHONPATH=. .venv/bin/python -W ignore -m quant.alpha.dashboard; } >> live/logs/alpha_monthly.log 2>&1
