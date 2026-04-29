#!/bin/bash
# 启动 Web 管理界面

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 python3，请先安装 Python 3"
    exit 1
fi

# 检查并安装依赖
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

echo "📦 激活虚拟环境并安装依赖..."
source venv/bin/activate
pip install -q -r requirements_web.txt

# 端口处理
DEFAULT_PORT="${WEB_APP_PORT:-5000}"
PORT="$DEFAULT_PORT"

is_port_in_use() {
    lsof -i tcp:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

release_port_if_webapp() {
    local port=$1
    local released=false
    if is_port_in_use "$port"; then
        echo "⚠️ 端口 $port 已被占用，尝试自动释放..."
        # 仅结束 web_app.py 相关进程
        local pids
        pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null)
        if [ -n "$pids" ]; then
            while IFS= read -r pid; do
                if ps -p "$pid" -o command= | grep -q "web_app.py"; then
                    echo "🛑 结束进程 $pid (web_app.py)"
                    kill -9 "$pid" >/dev/null 2>&1
                    released=true
                fi
            done <<< "$pids"
            sleep 1
        fi
    fi
    $released && return 0 || return 1
}

# 如果端口被占用，先尝试释放
if is_port_in_use "$PORT"; then
    if ! release_port_if_webapp "$PORT"; then
        echo "⚠️ 端口 $PORT 被其他程序占用，查找可用端口..."
        for candidate in $(seq $((PORT + 1)) $((PORT + 20))); do
            if ! is_port_in_use "$candidate"; then
                PORT=$candidate
                echo "✅ 使用新的端口: $PORT"
                break
            fi
        done
    else
        echo "✅ 端口 $PORT 已释放"
    fi
fi

if is_port_in_use "$PORT"; then
    echo "❌ 无法找到可用端口，请手动释放 5000 附近的端口后重试。"
    exit 1
fi

export WEB_APP_PORT="$PORT"

# 启动 Web 应用
echo "🚀 启动 Web 管理界面..."
echo "📍 访问地址: http://localhost:$PORT"
echo "按 Ctrl+C 停止服务"
echo ""

python3 web_app.py

