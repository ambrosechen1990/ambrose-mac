#!/bin/bash
# 兼容旧入口：转发到 run_Beatbot_tools.command
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/run_Beatbot_tools.command" "$@"
