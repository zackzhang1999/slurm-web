#!/bin/bash

# Slurm Monitor Startup Script

cd "$(dirname "$0")"

# Check if running as root (needed for some Slurm commands)
if [ "$EUID" -ne 0 ]; then 
    echo "注意: 某些功能可能需要 root 权限才能正常工作"
fi

# Check Python and dependencies
echo "检查依赖..."
python3 -c "import flask, flask_socketio" 2>/dev/null || {
    echo "安装依赖..."
    pip3 install flask flask-cors flask-socketio -q
}

# Set environment
export FLASK_APP=app.py
export PYTHONUNBUFFERED=1

echo "=========================================="
echo "  Slurm 集群监控系统"
echo "=========================================="
echo ""
echo "正在启动服务..."
echo "请在浏览器中访问: http://localhost:5000"
echo ""
echo "按 Ctrl+C 停止服务"
echo "=========================================="
echo ""

# Start the server
python3 app.py
