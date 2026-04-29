#!/bin/bash
# Appium 服务器启动脚本（1扫码配网）
# 此脚本会从 device_config.json 读取端口并启动 Appium 服务器

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 脚本路径
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# 优先从 common 目录读取配置文件（脚本在 common 目录下）
if [ -f "$SCRIPT_DIR/device_config.json" ]; then
    CONFIG_FILE="$SCRIPT_DIR/device_config.json"
    echo -e "${GREEN}✅ 使用 common 目录配置文件: $CONFIG_FILE${NC}"
elif [ -f "$(dirname "$SCRIPT_DIR")/device_config.json" ]; then
    CONFIG_FILE="$(dirname "$SCRIPT_DIR")/device_config.json"
    echo -e "${YELLOW}⚠️ 使用上级目录配置文件: $CONFIG_FILE${NC}"
else
CONFIG_FILE="$SCRIPT_DIR/device_config.json"
    echo -e "${RED}❌ 未找到配置文件，将使用默认路径: $CONFIG_FILE${NC}"
fi

# 默认 Android SDK 路径（按优先级顺序）
ANDROID_SDK_PATHS=(
    "$HOME/Library/Android/sdk"
    "$HOME/Android/Sdk"
    "/usr/local/share/android-sdk"
    "/opt/android-sdk"
)

# 查找 Android SDK
ANDROID_SDK_PATH=""
for path in "${ANDROID_SDK_PATHS[@]}"; do
    if [ -d "$path" ] && [ -d "$path/platform-tools" ]; then
        ANDROID_SDK_PATH="$path"
        echo -e "${GREEN}✅ 找到 Android SDK: $ANDROID_SDK_PATH${NC}"
        break
    fi
done

# 如果没找到，尝试从环境变量获取
if [ -z "$ANDROID_SDK_PATH" ]; then
    if [ -n "$ANDROID_HOME" ] && [ -d "$ANDROID_HOME" ]; then
        ANDROID_SDK_PATH="$ANDROID_HOME"
        echo -e "${GREEN}✅ 使用环境变量 ANDROID_HOME: $ANDROID_SDK_PATH${NC}"
    elif [ -n "$ANDROID_SDK_ROOT" ] && [ -d "$ANDROID_SDK_ROOT" ]; then
        ANDROID_SDK_PATH="$ANDROID_SDK_ROOT"
        echo -e "${GREEN}✅ 使用环境变量 ANDROID_SDK_ROOT: $ANDROID_SDK_PATH${NC}"
    fi
fi

# 设置环境变量（如果找到了 SDK）
if [ -n "$ANDROID_SDK_PATH" ]; then
    export ANDROID_HOME="$ANDROID_SDK_PATH"
    export ANDROID_SDK_ROOT="$ANDROID_SDK_PATH"
    export PATH="$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/tools"
    echo -e "${GREEN}✅ 环境变量已设置:${NC}"
    echo "   ANDROID_HOME=$ANDROID_HOME"
    echo "   ANDROID_SDK_ROOT=$ANDROID_SDK_ROOT"
else
    echo -e "${YELLOW}⚠️  未找到 Android SDK，继续执行（iOS 设备不需要）${NC}"
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
    echo -e "${RED}❌ 配置文件不存在: $CONFIG_FILE${NC}"
    exit 1
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

# 如果还是没有端口，使用默认值
if [ ${#PORTS[@]} -eq 0 ]; then
    echo -e "${YELLOW}⚠️  未找到端口配置，使用默认端口: 4725, 4726, 4727, 4728, 4729, 4735, 4736${NC}"
    PORTS=(4725 4726 4727 4728 4729 4735 4736)
fi

# 去重并排序端口
PORTS=($(printf '%s\n' "${PORTS[@]}" | sort -u))

echo -e "${GREEN}📋 将启动以下端口的 Appium 服务器: ${PORTS[*]}${NC}"

# 停止已运行的 Appium 服务器
echo -e "${YELLOW}🛑 停止已运行的 Appium 服务器...${NC}"
for port in "${PORTS[@]}"; do
    # 使用 lsof 查找占用端口的进程
    if command -v lsof &> /dev/null; then
        lsof -ti :$port | xargs kill -9 2>/dev/null
    fi
    # 备用方法：使用 pkill
    pkill -f "appium.*-p $port" 2>/dev/null
done
sleep 2

# 启动 Appium 服务器
echo -e "${GREEN}🚀 启动 Appium 服务器...${NC}"
APPIUM_PIDS=()
for port in "${PORTS[@]}"; do
    echo -e "${GREEN}   端口 $port${NC}"
    nohup appium -p $port > /tmp/appium_${port}.log 2>&1 &
    APPIUM_PIDS+=($!)
done

# 等待服务器启动
echo -e "${YELLOW}⏳ 等待服务器启动...${NC}"
sleep 8  # 增加等待时间，确保服务器完全启动

# 检查服务器状态
check_server() {
    local port=$1
    local max_attempts=3
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
    local response=$(curl -s http://127.0.0.1:$port/status 2>/dev/null)
        if [ -n "$response" ] && echo "$response" | grep -q "ready"; then
        echo -e "${GREEN}✅ Appium 服务器 (端口 $port) 运行正常${NC}"
        return 0
        fi
        
        if [ $attempt -lt $max_attempts ]; then
            sleep 2
            ((attempt++))
        else
            break
        fi
    done
    
    # 如果检查失败，再检查进程是否在运行
    if pgrep -f "appium.*-p $port" > /dev/null; then
        echo -e "${YELLOW}⚠️ Appium 服务器 (端口 $port) 进程在运行，但状态检查失败${NC}"
        echo "   查看日志: tail -f /tmp/appium_${port}.log"
        return 0  # 进程在运行，认为成功
    else
        echo -e "${RED}❌ Appium 服务器 (端口 $port) 启动失败${NC}"
        echo "   查看日志: tail -f /tmp/appium_${port}.log"
        return 1
    fi
}

# 检查所有服务器状态
SUCCESS_COUNT=0
for port in "${PORTS[@]}"; do
    if check_server $port; then
        ((SUCCESS_COUNT++))
    fi
done

echo ""
if [ $SUCCESS_COUNT -eq ${#PORTS[@]} ]; then
    echo -e "${GREEN}✅ 所有 Appium 服务器启动完成！${NC}"
else
    echo -e "${YELLOW}⚠️  部分 Appium 服务器启动失败 (成功: $SUCCESS_COUNT/${#PORTS[@]})${NC}"
fi
echo ""
echo "查看日志:"
for port in "${PORTS[@]}"; do
    echo "   tail -f /tmp/appium_${port}.log"
done
echo ""
echo "停止所有服务器:"
echo "   $SCRIPT_DIR/stop_appium.sh"

