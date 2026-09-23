#!/usr/bin/env bash
# 无头抓取渲染后的 DOM 文本（用于读取探针输出的断言文字）
# 用法: dump.sh <url 或 html 路径> <输出文件> [等待秒数]
#
# 和 shot.sh 同理：Windows 下 msedge.exe 是启动器，必须轮询等文件落盘。
set -u
EDGE="/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"

TARGET="$1"; OUT="$2"; WAIT="${3:-6}"
case "$TARGET" in
  http*|file:*) URL="$TARGET" ;;
  *) URL="file:///$(echo "$TARGET" | sed 's|\\|/|g; s|^/||')" ;;
esac

PROFILE="$(dirname "$OUT")/profile-dump"
WIN_PROFILE=$(echo "$PROFILE" | sed 's|/|\\|g')
mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"

"$EDGE" --headless=new --disable-gpu --no-sandbox --no-first-run \
  --user-data-dir="$WIN_PROFILE" \
  --window-size=1440,900 \
  --virtual-time-budget=$((WAIT * 1000)) \
  --dump-dom "$URL" > "$OUT" 2>/dev/null &

for i in $(seq 1 $((WAIT + 25))); do
  [ -s "$OUT" ] && { echo "OK  $OUT  (${i}s)"; exit 0; }
  sleep 1
done
echo "FAIL $OUT 未产出"
exit 1
