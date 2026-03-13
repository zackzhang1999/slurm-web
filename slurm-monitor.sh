#!/bin/bash

# Slurm Monitor - 自解压启动器
# 此脚本包含加密的项目数据，解压后自动运行 start.sh

set -e

# 配置
APP_NAME="slurm-monitor"
INSTALL_DIR="/opt/$APP_NAME"

# 解压数据
EXTRACT_DIR=$(mktemp -d)
trap "rm -rf $EXTRACT_DIR" EXIT

# 读取脚本自身的数据部分（从 __DATA__ 标记后开始）
SCRIPT_PATH="$(readlink -f "$0")"
DATA_START=$(grep -n "^__DATA__$" "$SCRIPT_PATH" | cut -d: -f1)
if [ -n "$DATA_START" ]; then
    tail -n +$((DATA_START + 1)) "$SCRIPT_PATH" | base64 -d | tar -xzf - -C "$EXTRACT_DIR"
fi

# 检查并安装依赖
echo "检查依赖..."
if ! python3 -c "import flask" 2>/dev/null; then
    echo "安装 Python 依赖..."
    pip3 install flask flask-cors flask-socketIO -q 2>/dev/null || pip3 install flask flask-cors flask-socketio -q
fi

# 进入安装目录
cd "$EXTRACT_DIR/$APP_NAME"

# 设置权限
chmod +x start.sh 2>/dev/null || true

# 运行 start.sh
echo "启动 Slurm 监控系统..."
exec ./start.sh

__DATA__
