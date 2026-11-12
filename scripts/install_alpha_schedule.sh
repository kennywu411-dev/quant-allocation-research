#!/bin/zsh
# 把因子线月度流水线装进本机 launchd（模板，需要你同意后再运行；默认没有安装）。卸载：加参数 --uninstall
set -e
DIR="$(cd "$(dirname "$0")" && pwd)/launchd"
REPO="$(cd "$DIR/../.." && pwd)"  # plist 是模板：__REPO__ 换成仓库目录，__HOME__ 换成家目录
name=com.quant.alpha-monthly
dst="$HOME/Library/LaunchAgents/$name.plist"
launchctl bootout "gui/$(id -u)/$name" 2>/dev/null || true
if [[ "$1" == "--uninstall" ]]; then rm -f "$dst"; echo "已卸载 $name"; exit 0; fi
sed -e "s#__REPO__#$REPO#g" -e "s#__HOME__#$HOME#g" "$DIR/$name.plist" > "$dst"
launchctl bootstrap "gui/$(id -u)" "$dst"
echo "已安装 $name"
