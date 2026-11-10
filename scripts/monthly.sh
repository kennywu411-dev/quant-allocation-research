#!/bin/zsh
# 每月 1 日：出本月调仓单 + 影子盘按新信号调仓 + 上月偏差报告（影子盘先调仓，上月区间才有终点）
cd "$(dirname "$0")/.." || exit 1
mkdir -p live/logs
{ date; .venv/bin/python -m quant.live.monthly; .venv/bin/python -m quant.live.shadow; .venv/bin/python -m quant.live.moomoo_paper --sync "$(date +%Y-%m)" || echo "模拟盘同步失败（OpenD 未开？）"; .venv/bin/python -m quant.live.review; } >> live/logs/monthly.log 2>&1
