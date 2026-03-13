#!/bin/bash
# Slurm Monitor 安装脚本

set -e

echo "=========================================="
echo "  Slurm Monitor 安装程序"
echo "=========================================="
echo ""

# 检查 root 权限
if [ "$EUID" -ne 0 ]; then 
    echo "请使用 sudo 运行此脚本"
    exit 1
fi

# 检查 Slurm
if ! command -v sinfo &> /dev/null; then
    echo "错误: 未检测到 Slurm，请先安装 Slurm"
    exit 1
fi

echo "✓ Slurm 已安装"
echo "  版本: $(sinfo -V)"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未检测到 Python3"
    exit 1
fi

echo "✓ Python3 已安装"
echo "  版本: $(python3 --version)"

# 安装 Flask
echo ""
echo "安装 Python 依赖..."
pip3 install flask flask-cors -q 2>/dev/null || pip3 install flask flask-cors --break-system-packages -q 2>/dev/null || {
    echo "警告: pip 安装失败，尝试使用系统包管理器"
    apt-get update -qq && apt-get install -y -qq python3-flask python3-flask-cors 2>/dev/null || true
}

# 创建日志目录
mkdir -p /var/log/slurm-monitor
chmod 755 /var/log/slurm-monitor

# 复制文件
INSTALL_DIR="/opt/slurm-web"
echo ""
echo "安装到 $INSTALL_DIR..."
mkdir -p $INSTALL_DIR
cp -r /root/slurm-web/* $INSTALL_DIR/

# 创建 systemd 服务
echo "创建 systemd 服务..."
cat > /etc/systemd/system/slurm-monitor.service << EOF
[Unit]
Description=Slurm Web Monitor
After=network.target slurmctld.service slurmd.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PYTHONUNBUFFERED=1"
ExecStart=/usr/bin/python3 $INSTALL_DIR/app.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/slurm-monitor/service.log
StandardError=append:/var/log/slurm-monitor/error.log

[Install]
WantedBy=multi-user.target
EOF

# 重新加载 systemd
systemctl daemon-reload

# 启动服务
echo ""
echo "启动服务..."
systemctl enable slurm-monitor
systemctl start slurm-monitor

sleep 2

# 检查服务状态
if systemctl is-active --quiet slurm-monitor; then
    echo ""
    echo "=========================================="
    echo "  ✓ 安装成功！"
    echo "=========================================="
    echo ""
    echo "访问地址:"
    IP=$(hostname -I | awk '{print $1}')
    echo "  - 本地: http://localhost:5000"
    echo "  - 网络: http://$IP:5000"
    echo ""
    echo "管理命令:"
    echo "  - 查看状态: systemctl status slurm-monitor"
    echo "  - 停止服务: systemctl stop slurm-monitor"
    echo "  - 重启服务: systemctl restart slurm-monitor"
    echo "  - 查看日志: journalctl -u slurm-monitor -f"
    echo ""
else
    echo ""
    echo "警告: 服务启动失败，请检查日志:"
    echo "  journalctl -u slurm-monitor -n 50"
    exit 1
fi
