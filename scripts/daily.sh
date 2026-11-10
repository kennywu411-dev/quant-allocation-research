#!/bin/zsh
# 每个工作日：记份额净值（回撤提醒）+ 影子盘标记；每月第一个工作日影子盘自动按新信号调仓
cd "$(dirname "$0")/.." || exit 1
mkdir -p live/logs
{ date; .venv/bin/python -m quant.live.ledger; .venv/bin/python -m quant.live.shadow; } >> live/logs/daily.log 2>&1
