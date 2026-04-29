#!/bin/bash
# Appium 服务器停止脚本（1扫码配网）
# 此脚本会从 device_config.json 读取端口并停止 Appium 服务器

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 脚本路径
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# 优先从 common 目录读取配置文件
if [ -f "$SCRIPT_DIR/common/device_config.json" ]; then
    CONFIG_FILE="$SCRIPT_DIR/common/device_config.json"
    echo -e "${GREEN}✅ 使用 common 目录配置文件: $CONFIG_FILE${NC}"
elif [ -f "$SCRIPT_DIR/device_config.json" ]; then
    CONFIG_FILE="$SCRIPT_DIR/device_config.json"
    echo -e "${YELLOW}⚠️ 使用根目录配置文件（建议使用 common/device_config.json）: $CONFIG_FILE${NC}"
else
CONFIG_FILE="$SCRIPT_DIR/device_config.json"
    echo -e "${RED}❌ 未找到配置文件，将使用默认路径: $CONFIG_FILE${NC}"
fi

# 获取端口列表
PORTS=()

# 从配置文件读取端口
if [ -f "$CONFIG_FILE" ]; then
    echo -e "${GREEN}📋 从配置文件读取端口: $CONFIG_FILE${NC}"
    if command -v python3 &> /dev/null; then
        while IFS= read -r port; do
            if [ -n "$port" ]; then
                PORTS+=("$port")
            fi
        done < <(python3 - "$CONFIG_FILE" <<'PY' 2>/dev/null
import json, sys
path = sys.argv[1]
try:
    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    for dev in config.get('device_configs', {}).values():
        port = dev.get('port')
        if port:
            print(port)
except Exception as exc:
    sys.exit(1)
PY
)
    elif command -v jq &> /dev/null; then
        while IFS= read -r port; do
            if [ -n "$port" ]; then
                PORTS+=("$port")
            fi
        done < <(jq -r '.device_configs[].port // empty' "$CONFIG_FILE" 2>/dev/null)
    else
        echo -e "${RED}❌ 需要 python3 或 jq 来解析配置文件${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️  配置文件不存在: $CONFIG_FILE${NC}"
    echo -e "${YELLOW}   尝试停止所有 Appium 进程...${NC}"
    pkill -f "appium" 2>/dev/null
    echo -e "${GREEN}✅ 已尝试停止所有 Appium 进程${NC}"
    exit 0
fi

# 如果从配置文件读取失败，尝试从参数获取
if [ ${#PORTS[@]} -eq 0 ]; then
    if [ $# -gt 0 ]; then
        for arg in "$@"; do
            if [[ "$arg" =~ ^[0-9]+$ ]]; then
                PORTS+=($arg)
            fi
        done
    fi
fi

# 如果还是没有端口，停止所有 Appium 进程
if [ ${#PORTS[@]} -eq 0 ]; then
    echo -e "${YELLOW}⚠️  未找到端口配置，停止所有 Appium 进程...${NC}"
    pkill -f "appium" 2>/dev/null
    echo -e "${GREEN}✅ 已停止所有 Appium 进程${NC}"
    exit 0
fi

# 去重并排序端口
PORTS=($(printf '%s\n' "${PORTS[@]}" | sort -u))

echo -e "${GREEN}📋 将停止以下端口的 Appium 服务器: ${PORTS[*]}${NC}"

# 停止 Appium 服务器
STOPPED_COUNT=0
FAILED_COUNT=0

for port in "${PORTS[@]}"; do
    echo -e "${YELLOW}🛑 停止端口 $port 的 Appium 服务器...${NC}"
    
    # 方法1: 使用 lsof 查找占用端口的进程
    STOPPED=false
    if command -v lsof &> /dev/null; then
        PIDS=$(lsof -ti :$port 2>/dev/null)
        if [ -n "$PIDS" ]; then
            for pid in $PIDS; do
                if [ -n "$pid" ]; then
                    kill -9 $pid 2>/dev/null
                    STOPPED=true
                fi
            done
        fi
    fi
    
    # 方法2: 使用 pkill（备用方法）
    if [ "$STOPPED" = false ]; then
        if pkill -f "appium.*-p $port" 2>/dev/null; then
            STOPPED=true
        fi
    fi
    
    # 验证是否已停止
    sleep 1
    if command -v lsof &> /dev/null; then
        if ! lsof -ti :$port &>/dev/null; then
            echo -e "${GREEN}✅ 端口 $port 的 Appium 服务器已停止${NC}"
            ((STOPPED_COUNT++))
        else
            echo -e "${RED}❌ 端口 $port 的 Appium 服务器停止失败${NC}"
            ((FAILED_COUNT++))
        fi
    else
        # 如果没有 lsof，假设已停止
        echo -e "${GREEN}✅ 已尝试停止端口 $port 的 Appium 服务器${NC}"
        ((STOPPED_COUNT++))
    fi
done

echo ""
if [ $FAILED_COUNT -eq 0 ]; then
    echo -e "${GREEN}✅ 所有 Appium 服务器已停止！ (成功: $STOPPED_COUNT/${#PORTS[@]})${NC}"
else
    echo -e "${YELLOW}⚠️  部分 Appium 服务器停止失败 (成功: $STOPPED_COUNT/${#PORTS[@]}, 失败: $FAILED_COUNT)${NC}"
    echo -e "${YELLOW}   可以尝试手动停止: pkill -f 'appium'${NC}"
fi

