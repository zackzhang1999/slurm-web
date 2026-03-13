#!/usr/bin/env python3
import sys
import os
import tempfile
import shutil
import subprocess

APP_NAME = "slurm-monitor"

def main():
    # 获取临时目录
    tmpdir = tempfile.mkdtemp()
    print(f"临时目录: {tmpdir}")
    
    # 获取当前目录
    src_dir = os.getcwd()
    
    # 复制项目文件到临时目录
    print("正在复制文件...")
    dst_dir = os.path.join(tmpdir, APP_NAME)
    shutil.copytree(src_dir, dst_dir, 
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git', '*.egg-info'))
    
    # 创建打包目录
    build_dir = os.path.join(dst_dir, 'build')
    os.makedirs(build_dir, exist_ok=True)
    
    # 运行 PyInstaller
    print("正在打包，请稍候...")
    os.chdir(dst_dir)
    
    cmd = [
        'pyinstaller',
        '--name', APP_NAME,
        '--onefile',
        '--add-data', 'templates:templates',
        '--add-data', 'static:static',
        '--hidden-import', 'flask',
        '--hidden-import', 'flask_socketio',
        '--hidden-import', 'flask_cors',
        '--collect-all', 'flask_socketio',
        '--collect-all', 'engineio',
        '--collect-all', 'socketio',
        '--console',
        'app.py'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("打包失败!")
        print(result.stderr)
        sys.exit(1)
    
    # 找到生成的可执行文件
    exe_path = os.path.join(dst_dir, 'dist', APP_NAME)
    
    if os.path.exists(exe_path):
        # 复制到当前目录
        final_path = os.path.join(src_dir, APP_NAME)
        shutil.copy(exe_path, final_path)
        os.chmod(final_path, 0o755)
        
        print(f"\n打包成功!")
        print(f"可执行文件: {final_path}")
        
        # 清理临时目录
        shutil.rmtree(tmpdir)
    else:
        print("未找到生成的可执行文件")
        sys.exit(1)

if __name__ == '__main__':
    main()
