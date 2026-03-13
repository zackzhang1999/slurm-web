#!/bin/bash
# 打包脚本 - 将项目打包成自解压可执行文件

cd "$(dirname "$0")"

echo "正在打包 Slurm 监控系统..."

# 1. 排除不必要的文件
EXCLUDE_DIRS="__pycache__ *.pyc .git *.egg-info build dist *.spec"
EXCLUDE_FILES="slurm-monitor.sh build.py"

# 2. 创建临时目录
TEMP_DIR=$(mktemp -d)
PROJECT_DIR="$TEMP_DIR/slurm-monitor"

# 3. 复制项目文件
mkdir -p "$PROJECT_DIR"
rsync -av --exclude='__pycache__' --exclude='*.pyc' --exclude='.git' --exclude='build' --exclude='dist' --exclude='*.spec' --exclude='slurm-monitor.sh' --exclude='build.py' . "$PROJECT_DIR/"

# 4. 打包成 tar.gz
echo "创建压缩包..."
tar -czf - -C "$TEMP_DIR" slurm-monitor | base64 > data.tar.b64

# 5. 创建最终的可执行文件
echo "创建自解压可执行文件..."
{
    cat slurm-monitor.sh
    echo ""
    cat data.tar.b64
} > slurm-monitor

# 6. 清理
rm -rf "$TEMP_DIR" data.tar.b64

# 7. 设置执行权限
chmod +x slurm-monitor

echo "打包完成!"
echo "可执行文件: slurm-monitor"
echo ""
echo "使用方法: ./slurm-monitor"
