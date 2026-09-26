#!/usr/bin/env bash
# 无头截图工具
# 用法: shot.sh <url 或 html 路径> <输出png> [宽] [高] [等待秒数] [像素密度]
#
# 注意：Windows 下 msedge.exe 是启动器，会立刻返回并把真正的渲染交给子进程，
# 如果不等待，进程会在截图落盘前被回收 —— 所以必须在同一次调用里轮询等文件出现。
#
# 第 6 个参数是 device-scale-factor：CSS 视口尺寸不变（布局完全一致），
# 只提高光栅密度，用来放大看牌的细节。

set -u
EDGE="/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"

TARGET="$1"; OUT_PNG="$2"
W="${3:-1440}"; H="${4:-900}"; WAIT="${5:-8}"; SCALE="${6:-1}"

case "$TARGET" in
  http*|file:*) URL="$TARGET" ;;
  *) URL="file:///$(echo "$TARGET" | sed 's|\\|/|g; s|^/||')" ;;
esac

# 转成 Windows 路径（Edge 只认反斜杠）
WIN_OUT=$(echo "$OUT_PNG" | sed 's|/|\\|g')
PROFILE_DIR="$(dirname "$OUT_PNG")/profile"
WIN_PROFILE=$(echo "$PROFILE_DIR" | sed 's|/|\\|g')
rm -f "$OUT_PNG"
mkdir -p "$(dirname "$OUT_PNG")"

"$EDGE" --headless=new --disable-gpu --no-sandbox --no-first-run \
  --hide-scrollbars --force-device-scale-factor="$SCALE" \
  ${SHOT_FLAGS:-} \
  --user-data-dir="$WIN_PROFILE" \
  --screenshot="$WIN_OUT" \
  --window-size="$W,$H" \
  --virtual-time-budget=$((WAIT * 1000)) \
  "$URL" >/dev/null 2>&1 &

for i in $(seq 1 $((WAIT + 25))); do
  [ -s "$OUT_PNG" ] && { echo "OK  $OUT_PNG  (${i}s)"; exit 0; }
  sleep 1
done
echo "FAIL $OUT_PNG 未产出"
exit 1
