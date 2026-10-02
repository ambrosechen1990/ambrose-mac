#!/bin/bash
# 双击启动 macOS 版「视频标定矫正」
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

PY=""
for c in python3.11 python3.12 python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
  if command -v "$c" >/dev/null 2>&1; then
    PY="$(command -v "$c")"
    break
  fi
done

if [[ -z "$PY" ]]; then
  osascript -e 'display dialog "未找到 python3，请先安装 Python 3。" buttons {"好"} default button 1'
  exit 1
fi

exec "$PY" "$DIR/视频标定矫正.py"
