#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "未找到 python3，请先安装 Python 3.10+"
  exit 1
fi

VENV=".venv_run"
if [ ! -d "$VENV" ]; then
  "$PYTHON_BIN" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "启动 Beatbot 软测工具 (macOS)..."
cd 主程序
# 优先 Beatbot.py；兼容旧入口
if [ -f "Beatbot.py" ]; then
  python Beatbot.py
elif [ -f "Beatbot-mac.py" ]; then
  python Beatbot-mac.py
elif [ -f "老版/Softwaretest.py" ]; then
  python 老版/Softwaretest.py
elif [ -f "Softwaretest.py" ]; then
  python Softwaretest.py
fi
