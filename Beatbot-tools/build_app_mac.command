#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
python3 工具脚本/打包脚本_mac.py "$@"
