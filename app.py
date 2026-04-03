#!/usr/bin/env python3
"""
Slurm Monitor - A comprehensive web-based monitoring system for Slurm Workload Manager
With Socket.IO real-time updates
Author: Assistant
Version: 1.3.0
"""

import os
import re
import json
import subprocess
import datetime
import threading
import time
import uuid
import socket
import paramiko
import shutil
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, jsonify, request, Response, session, redirect, url_for, send_file as flask_send_file
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'slurm-monitor-secret-key-change-in-production'
app.config['JSON_SORT_KEYS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(minutes=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# 动态获取项目根目录
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_ROOT, 'config.json')
USER_DB_FILE = os.path.join(APP_ROOT, 'users.json')

# Load config
def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except:
        return {'admin_password': 'admin888', 'password_enabled': True}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

# ============== 用户管理 ==============

def load_users():
    try:
        with open(USER_DB_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USER_DB_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def init_user(username):
    """初始化用户，默认为首次登录"""
    users = load_users()
    if username not in users:
        return None
    return users.get(username)

def get_user(username):
    """获取用户信息"""
    users = load_users()
    return users.get(username)

def register_user(username, password='123456'):
    """注册新用户"""
    users = load_users()
    if username in users:
        return users[username]
    users[username] = {
        'password': password,
        'is_first_login': True,
        'created_at': datetime.datetime.now().isoformat()
    }
    save_users(users)
    return users[username]

def verify_user_password(username, password):
    """验证用户密码"""
    user = get_user(username)
    if not user:
        return False
    return user.get('password') == password

def change_user_password(username, new_password):
    """修改用户密码"""
    users = load_users()
    if username in users:
        users[username]['password'] = new_password
        users[username]['is_first_login'] = False
        users[username]['changed_at'] = datetime.datetime.now().isoformat()
        save_users(users)
        return True
    return False

# ============== 登录相关路由 ==============

@app.route('/login')
def login_page():
    """登录页面"""
    if 'user_type' in session:
        return redirect('/')
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    """登录API"""
    data = request.json
    login_type = data.get('type')
    
    if login_type == 'admin':
        password = data.get('password', '')
        config = load_config()
        admin_password = config.get('admin_password', 'admin888')
        
        if password == admin_password:
            session['user_type'] = 'admin'
            session['username'] = 'admin'
            session.permanent = True
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': '管理员密码错误'})
    
    elif login_type == 'user':
        username = data.get('username', '')
        password = data.get('password', '')
        new_password = data.get('newPassword')
        
        if not username:
            return jsonify({'success': False, 'message': '请输入用户名'})
        
        # 从 Slurm 获取用户列表
        output = run_command("sacctmgr -n list user format=user%20 2>/dev/null")
        slurm_users = []
        if output and not output.startswith("Error"):
            slurm_users = [line.strip() for line in output.strip().split('\n') if line.strip()]
        
        # 检查用户是否在 Slurm 用户列表中
        if username not in slurm_users:
            return jsonify({'success': False, 'message': '用户不存在，请检查用户名'})
        
        # 检查用户是否已注册
        user = get_user(username)
        
        if not user:
            # Slurm 用户，自动注册，默认密码123456
            register_user(username, '123456')
        
        # 再次获取用户信息
        user = get_user(username)
        
        # 验证密码
        if user.get('password') != password:
            return jsonify({'success': False, 'message': '密码错误'})
        
        # 检查是否首次登录需要修改密码
        if user.get('is_first_login') and not new_password:
            return jsonify({'success': False, 'message': 'first_login', 'username': username})
        
        # 如果提供了新密码，修改密码
        if new_password:
            change_user_password(username, new_password)
        
        session['user_type'] = 'user'
        session['username'] = username
        session.permanent = True
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': '无效的登录类型'})

@app.route('/api/check-first-login', methods=['POST'])
def api_check_first_login():
    """检查是否为首次登录"""
    data = request.json
    username = data.get('username', '')
    password = data.get('password', '')
    
    if not username:
        return jsonify({'firstLogin': False})
    
    # 从 Slurm 获取用户列表
    output = run_command("sacctmgr -n list user format=user%20 2>/dev/null")
    slurm_users = []
    if output and not output.startswith("Error"):
        slurm_users = [line.strip() for line in output.strip().split('\n') if line.strip()]
    
    # 检查用户是否在 Slurm 用户列表中
    if username not in slurm_users:
        return jsonify({'firstLogin': False, 'error': '用户不存在'})
    
    # 检查用户是否已注册
    user = get_user(username)
    
    if not user:
        # Slurm 用户，自动注册
        register_user(username, '123456')
    
    # 再次获取用户信息
    user = get_user(username)
    
    return jsonify({'firstLogin': user.get('is_first_login', True) if user else True})

@app.route('/api/logout', methods=['POST'])
def api_logout():
    """登出API"""
    session.clear()
    return jsonify({'success': True})

@app.route('/api/current-user', methods=['GET'])
def api_current_user():
    """获取当前登录用户信息"""
    if 'user_type' not in session:
        return jsonify({'logged_in': False})
    
    return jsonify({
        'logged_in': True,
        'user_type': session.get('user_type'),
        'username': session.get('username')
    })

def require_admin():
    """检查是否为管理员"""
    return session.get('user_type') == 'admin'

def require_login():
    """检查是否已登录"""
    return 'user_type' in session

# Initialize SocketIO with threading mode for better compatibility
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=False, engineio_logger=False)

# ============== Slurm Command Helpers ==============

def run_command(cmd, timeout=30):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return f"Error: {result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Command timeout"
    except Exception as e:
        return f"Error: {str(e)}"

def parse_sinfo():
    """Parse sinfo output - get unique nodes"""
    output = run_command("sinfo -N -o '%N|%T|%c|%m|%e|%O|%G|%P|%C|%z'")
    nodes = []
    seen = set()
    if output and not output.startswith("Error"):
        lines = output.split('\n')[1:]  # Skip header
        for line in lines:
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 10:
                    node_name = parts[0]
                    # Avoid duplicates (same node in multiple partitions)
                    if node_name in seen:
                        continue
                    seen.add(node_name)
                    nodes.append({
                        'name': node_name,
                        'state': parts[1],
                        'cpus': parts[2],
                        'memory': parts[3],
                        'free_mem': parts[4],
                        'load': parts[5],
                        'gres': parts[6] if parts[6] else 'none',
                        'partition': parts[7],
                        'cpu_alloc': parts[8],
                        'sockets_cores_threads': parts[9]
                    })
    return nodes

def parse_squeue():
    """Parse squeue output"""
    # %V = SubmitTime, %S = StartTime, %r = Reason (for pending jobs)
    output = run_command("squeue -o '%i|%P|%j|%u|%t|%M|%D|%R|%C|%m|%N|%b|%Q|%V|%S|%e|%Z|%r'")
    jobs = []
    if output and not output.startswith("Error"):
        lines = output.split('\n')[1:]
        for line in lines:
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 18:
                    jobs.append({
                        'job_id': parts[0],
                        'partition': parts[1],
                        'name': parts[2],
                        'user': parts[3],
                        'state': parts[4],
                        'time': parts[5],
                        'nodes': parts[6],
                        'nodelist': parts[7],
                        'cpus': parts[8],
                        'memory': parts[9],
                        'allocated_nodes': parts[10],
                        'gres': parts[11] if parts[11] else 'none',
                        'priority': parts[12],
                        'submit_time': parts[13],
                        'start_time': parts[14],
                        'time_left': parts[15],
                        'work_dir': parts[16],
                        'reason': parts[17] if parts[17] else '-'
                    })
    return jobs

def parse_sacct_history(hours=24):
    """Parse sacct for job history"""
    output = run_command(
        f"sacct -a -X --format=JobID,JobName,User,Partition,State,ExitCode,"
        f"Elapsed,CPUTime,MaxRSS,ReqCPUS,ReqMem,AllocNodes,NTasks -S now-{hours}hours 2>/dev/null"
    )
    jobs = []
    if output and not output.startswith("Error"):
        lines = output.split('\n')[2:]  # Skip headers
        for line in lines:
            parts = line.split()
            if len(parts) >= 6:
                jobs.append({
                    'job_id': parts[0],
                    'name': parts[1] if len(parts) > 1 else 'N/A',
                    'user': parts[2] if len(parts) > 2 else 'N/A',
                    'partition': parts[3] if len(parts) > 3 else 'N/A',
                    'state': parts[4] if len(parts) > 4 else 'N/A',
                    'exit_code': parts[5] if len(parts) > 5 else 'N/A'
                })
    return jobs

def parse_partitions():
    """Parse partition information"""
    output = run_command("scontrol show partition")
    partitions = []
    if output and not output.startswith("Error"):
        blocks = re.split(r'\n\n', output)
        for block in blocks:
            if 'PartitionName' in block:
                part = {}
                for line in block.split('\n'):
                    for match in re.finditer(r'(\w+)=([^\s]+)', line):
                        key, value = match.groups()
                        part[key.lower()] = value
                if part:
                    partitions.append(part)
    return partitions

def parse_disk_quota():
    """Parse disk quota information from repquota"""
    quotas = {'users': [], 'summary': {}}
    
    # Get all user quotas with -avus flag
    output = run_command("repquota -avus 2>/dev/null")
    if output and not output.startswith("Error"):
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('*') or line.startswith('Block') or line.startswith('User') or line.startswith('-'):
                continue
            parts = line.split()
            if len(parts) >= 7:
                try:
                    used_space = parts[2] if len(parts) > 2 else '0'
                    soft_limit = parts[3] if len(parts) > 3 else '0'
                    hard_limit = parts[4] if len(parts) > 4 else '0'
                    used_files = parts[6] if len(parts) > 6 else '0'
                    soft_files = parts[7] if len(parts) > 7 else '0'
                    hard_files = parts[8] if len(parts) > 8 else '0'
                    
                    user = {
                        'type': 'user',
                        'name': parts[0],
                        'used_space': used_space,
                        'soft_limit': soft_limit,
                        'hard_limit': hard_limit,
                        'used_files': used_files,
                        'soft_files': soft_files,
                        'hard_files': hard_files
                    }
                    quotas['users'].append(user)
                except Exception as e:
                    pass
    
    # Calculate summary
    total_users = len(quotas['users'])
    over_limit_users = 0
    for u in quotas['users']:
        try:
            if u['hard_limit'] not in ['0', '-', '']:
                used = float(u['used_space'])
                hard = float(u['hard_limit'])
                if used >= hard and hard > 0:
                    over_limit_users += 1
        except:
            pass
    
    quotas['summary'] = {
        'total_users': total_users,
        'over_limit_users': over_limit_users
    }
    
    return quotas

def parse_reservations():
    """Parse reservation information from scontrol"""
    output = run_command("scontrol show reservation")
    reservations = []
    if output and not output.startswith("Error") and output.strip():
        if "No reservations" in output:
            return []
        blocks = re.split(r'\n\n', output)
        for block in blocks:
            if 'ReservationName' in block:
                res = {}
                for line in block.split('\n'):
                    for match in re.finditer(r'(\w+)=(.+?)(?=\s+\w+=|$)', line):
                        key, value = match.groups()
                        key = key.lower()
                        value = value.strip()
                        if value and value.lower() not in ['null', 'n/a'] and not value.startswith('('):
                            res[key] = value
                if res:
                    reservations.append(res)
    return reservations

def parse_node_details(node_name):
    """Get detailed node information"""
    output = run_command(f"scontrol show node {node_name}")
    details = {}
    if output and not output.startswith("Error"):
        for line in output.split('\n'):
            for match in re.finditer(r'(\w+)=([^\s]+)', line):
                key, value = match.groups()
                details[key.lower()] = value
    return details

def parse_sdiag():
    """Parse sdiag for scheduler statistics"""
    output = run_command("sdiag")
    stats = {}
    if output and not output.startswith("Error"):
        lines = output.split('\n')
        current_section = None
        for line in lines:
            if 'Main scheduler statistics' in line:
                current_section = 'scheduler'
                stats['scheduler'] = {}
            elif 'Remote Procedure Call statistics' in line:
                current_section = 'rpc'
                stats['rpc'] = {}
            elif 'Pending RPC statistics' in line:
                current_section = 'pending_rpc'
                stats['pending_rpc'] = {}
            elif ':' in line and current_section:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip().lower().replace(' ', '_')
                    value = parts[1].strip()
                    stats[current_section][key] = value
    return stats

def get_user_resource_usage(hours=24):
    """Get CPU time and GPU time per user from sacct"""
    # Get job details with TRES (Trackable Resources) information
    output = run_command(
        f"sacct -a -X --format=User,JobID,Elapsed,CPUTime,AllocTRES,State -S now-{hours}hours --parsable2 --noheader 2>/dev/null || echo ''"
    )
    
    user_stats = {}
    total_cpu_minutes = 0
    total_gpu_minutes = 0
    
    if output and not output.startswith("Error") and output.strip() and 'Slurm accounting storage is disabled' not in output:
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 6:
                user = parts[0]
                job_id = parts[1]
                elapsed = parts[2]
                cpu_time = parts[3]
                alloc_tres = parts[4]
                state = parts[5]
                
                # Initialize user entry
                if user not in user_stats:
                    user_stats[user] = {
                        'cpu_minutes': 0,
                        'gpu_minutes': 0,
                        'jobs': 0,
                        'gpu_jobs': 0
                    }
                
                user_stats[user]['jobs'] += 1
                
                # Parse CPU time to minutes (CPUTime format is typically "HH:MM:SS" or "D-HH:MM:SS")
                cpu_seconds = parse_time_to_seconds(cpu_time)
                cpu_minutes = cpu_seconds / 60.0
                user_stats[user]['cpu_minutes'] += cpu_minutes
                total_cpu_minutes += cpu_minutes
                
                # Check if job used GPU
                gpu_count = 0
                if alloc_tres and 'gpu' in alloc_tres.lower():
                    # Extract GPU count from AllocTRES string like "gres/gpu=2"
                    import re
                    gpu_match = re.search(r'gres/gpu[=:](\d+)', alloc_tres, re.IGNORECASE)
                    if gpu_match:
                        gpu_count = int(gpu_match.group(1))
                
                if gpu_count > 0:
                    user_stats[user]['gpu_jobs'] += 1
                    # GPU time = elapsed time in minutes * GPU count
                    elapsed_seconds = parse_time_to_seconds(elapsed)
                    elapsed_minutes = elapsed_seconds / 60.0
                    gpu_minutes = elapsed_minutes * gpu_count
                    user_stats[user]['gpu_minutes'] += gpu_minutes
                    total_gpu_minutes += gpu_minutes
    
    # Build result with percentages
    result = []
    for user, stats in user_stats.items():
        cpu_percent = (stats['cpu_minutes'] / total_cpu_minutes * 100) if total_cpu_minutes > 0 else 0
        gpu_percent = (stats['gpu_minutes'] / total_gpu_minutes * 100) if total_gpu_minutes > 0 else 0
        
        result.append({
            'user': user,
            'cpu_minutes': round(stats['cpu_minutes'], 1),
            'gpu_minutes': round(stats['gpu_minutes'], 1),
            'jobs': stats['jobs'],
            'gpu_jobs': stats['gpu_jobs'],
            'cpu_percent': round(cpu_percent, 1),
            'gpu_percent': round(gpu_percent, 1)
        })
    
    # Sort by CPU minutes descending
    result.sort(key=lambda x: x['cpu_minutes'], reverse=True)
    
    return {
        'users': result,
        'total_cpu_minutes': round(total_cpu_minutes, 1),
        'total_gpu_minutes': round(total_gpu_minutes, 1)
    }

def parse_time_to_seconds(time_str):
    """Convert time string (HH:MM:SS or D-HH:MM:SS) to seconds"""
    if not time_str or time_str == 'N/A':
        return 0
    
    try:
        # Handle format like "1-12:30:00" (1 day, 12 hours, 30 minutes, 0 seconds)
        days = 0
        if '-' in time_str:
            day_part, time_str = time_str.split('-')
            days = int(day_part)
        
        parts = time_str.split(':')
        if len(parts) == 3:
            hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
            return days * 86400 + hours * 3600 + minutes * 60 + seconds
        elif len(parts) == 2:
            minutes, seconds = int(parts[0]), int(parts[1])
            return days * 86400 + minutes * 60 + seconds
    except:
        pass
    
    return 0

def format_seconds_to_time(total_seconds):
    """Convert seconds to HH:MM:SS format"""
    if total_seconds == 0:
        return '00:00:00'
    
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if hours >= 24:
        days = hours // 24
        hours = hours % 24
        return f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}"
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def parse_sreport_cluster_usage():
    """Parse sreport for cluster usage"""
    output = run_command("sreport cluster utilization -t percent --format=Cluster,Allocated,Down,Idle,Reported 2>/dev/null")
    usage = []
    if output and not output.startswith("Error"):
        lines = output.split('\n')[2:]
        for line in lines:
            parts = line.split()
            if len(parts) >= 4:
                usage.append({
                    'cluster': parts[0],
                    'allocated': parts[1],
                    'down': parts[2],
                    'idle': parts[3],
                    'reported': parts[4] if len(parts) > 4 else 'N/A'
                })
    return usage

# ============== GPU Information Helpers ==============

def has_local_nvidia_smi():
    """Check if nvidia-smi is available locally"""
    try:
        result = subprocess.run(
            "which nvidia-smi",
            shell=True, capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except:
        return False


def get_gpu_nodes():
    """Get list of nodes with GPU resources from Slurm configuration"""
    gpu_nodes = []
    
    # Try to get GPU nodes from sinfo
    output = run_command("sinfo -N -o '%N|%G' --noheader")
    if output and not output.startswith("Error"):
        seen = set()
        for line in output.strip().split('\n'):
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 2:
                    node_name = parts[0].strip()
                    gres = parts[1].strip()
                    # Check if node has GPU (gres contains 'gpu')
                    if 'gpu' in gres.lower() and node_name not in seen:
                        seen.add(node_name)
                        # Extract GPU count from gres if available
                        gpu_count = 0
                        gpu_match = re.search(r'gpu:\d+', gres, re.IGNORECASE)
                        if gpu_match:
                            gpu_count = int(gpu_match.group().split(':')[1])
                        gpu_nodes.append({
                            'name': node_name,
                            'gres': gres,
                            'gpu_count': gpu_count
                        })
    
    # If sinfo didn't return results, try slurm.conf
    if not gpu_nodes:
        conf = parse_slurm_conf()
        for node in conf.get('nodes', []):
            gres = node.get('gres', '')
            if 'gpu' in gres.lower():
                node_names = node.get('nodename', '')
                # Handle node ranges like "node[01-04]"
                if '[' in node_names:
                    # Expand node range
                    output = run_command(f"scontrol show hostnames {node_names}")
                    if output and not output.startswith("Error"):
                        for name in output.strip().split('\n'):
                            gpu_count = 0
                            gpu_match = re.search(r'gpu=(\d+)', gres, re.IGNORECASE)
                            if gpu_match:
                                gpu_count = int(gpu_match.group(1))
                            gpu_nodes.append({
                                'name': name,
                                'gres': gres,
                                'gpu_count': gpu_count
                            })
                else:
                    gpu_count = 0
                    gpu_match = re.search(r'gpu=(\d+)', gres, re.IGNORECASE)
                    if gpu_match:
                        gpu_count = int(gpu_match.group(1))
                    gpu_nodes.append({
                        'name': node_names,
                        'gres': gres,
                        'gpu_count': gpu_count
                    })
    
    return gpu_nodes


def run_ssh_command(node, cmd, timeout=30):
    """Run command on remote node via SSH"""
    ssh_cmd = f"ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes {node} '{cmd}'"
    return run_command(ssh_cmd, timeout)


def parse_nvidia_smi_from_node(node_name):
    """Get GPU information from a specific node via SSH"""
    # Try full query first
    output = run_ssh_command(
        node_name,
        "nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,"
        "memory.used,memory.total,power.draw,power.limit,persistence_mode,ecc.mode,"
        "compute_mode,pci.bus_id,fan.speed,clocks.current.sm,uuid "
        "--format=csv,noheader,nounits 2>/dev/null"
    )
    
    gpus = []
    
    # If full query fails, try basic query with power
    if not output or output.startswith("Error") or "Segmentation" in output or "command not found" in output.lower():
        output = run_ssh_command(
            node_name,
            "nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,"
            "memory.used,memory.total,power.draw --format=csv,noheader,nounits 2>/dev/null"
        )
        if output and not output.startswith("Error"):
            lines = output.strip().split('\n')
            for line in lines:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 7:
                    gpus.append({
                        'index': parts[0],
                        'name': parts[1],
                        'temperature': parts[2],
                        'utilization': parts[3],
                        'memory_used': parts[4],
                        'memory_total': parts[5],
                        'power_draw': parts[6] if len(parts) > 6 and parts[6] else 'N/A',
                        'power_limit': 'N/A',
                        'persistence_mode': 'N/A',
                        'ecc_mode': 'N/A',
                        'compute_mode': 'N/A',
                        'pci_bus_id': 'N/A',
                        'fan_speed': 'N/A',
                        'clocks_sm': 'N/A',
                        'uuid': 'N/A',
                        'node': node_name
                    })
    else:
        if output and not output.startswith("Error"):
            lines = output.strip().split('\n')
            for line in lines:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 15:
                    gpus.append({
                        'index': parts[0],
                        'name': parts[1],
                        'temperature': parts[2],
                        'utilization': parts[3],
                        'memory_used': parts[4],
                        'memory_total': parts[5],
                        'power_draw': parts[6] if len(parts) > 6 else 'N/A',
                        'power_limit': parts[7] if len(parts) > 7 else 'N/A',
                        'persistence_mode': parts[8] if len(parts) > 8 else 'N/A',
                        'ecc_mode': parts[9] if len(parts) > 9 else 'N/A',
                        'compute_mode': parts[10] if len(parts) > 10 else 'N/A',
                        'pci_bus_id': parts[11] if len(parts) > 11 else 'N/A',
                        'fan_speed': parts[12] if len(parts) > 12 else 'N/A',
                        'clocks_sm': parts[13] if len(parts) > 13 else 'N/A',
                        'uuid': parts[14] if len(parts) > 14 else 'N/A',
                        'node': node_name
                    })
    
    return gpus


def parse_nvidia_smi():
    """Get GPU information from nvidia-smi
    
    If local nvidia-smi is available, use it.
    Otherwise, SSH to compute nodes with GPUs to get information.
    """
    # First, try local nvidia-smi
    if has_local_nvidia_smi():
        # Try full query first
        output = run_command(
            "nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,"
            "memory.used,memory.total,power.draw,power.limit,persistence_mode,ecc.mode,"
            "compute_mode,pci.bus_id,fan.speed,clocks.current.sm,uuid "
            "--format=csv,noheader,nounits 2>/dev/null"
        )
        
        # If full query fails, try basic query with power
        if not output or output.startswith("Error") or "Segmentation" in output:
            output = run_command(
                "nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,"
                "memory.used,memory.total,power.draw --format=csv,noheader,nounits 2>/dev/null"
            )
            gpus = []
            if output and not output.startswith("Error"):
                lines = output.strip().split('\n')
                for line in lines:
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) >= 7:
                        gpus.append({
                            'index': parts[0],
                            'name': parts[1],
                            'temperature': parts[2],
                            'utilization': parts[3],
                            'memory_used': parts[4],
                            'memory_total': parts[5],
                            'power_draw': parts[6] if len(parts) > 6 and parts[6] else 'N/A',
                            'power_limit': 'N/A',
                            'persistence_mode': 'N/A',
                            'ecc_mode': 'N/A',
                            'compute_mode': 'N/A',
                            'pci_bus_id': 'N/A',
                            'fan_speed': 'N/A',
                            'clocks_sm': 'N/A',
                            'uuid': 'N/A',
                            'node': 'localhost'
                        })
            return gpus
        
        gpus = []
        if output and not output.startswith("Error"):
            lines = output.strip().split('\n')
            for line in lines:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 15:
                    gpus.append({
                        'index': parts[0],
                        'name': parts[1],
                        'temperature': parts[2],
                        'utilization': parts[3],
                        'memory_used': parts[4],
                        'memory_total': parts[5],
                        'power_draw': parts[6] if len(parts) > 6 else 'N/A',
                        'power_limit': parts[7] if len(parts) > 7 else 'N/A',
                        'persistence_mode': parts[8] if len(parts) > 8 else 'N/A',
                        'ecc_mode': parts[9] if len(parts) > 9 else 'N/A',
                        'compute_mode': parts[10] if len(parts) > 10 else 'N/A',
                        'pci_bus_id': parts[11] if len(parts) > 11 else 'N/A',
                        'fan_speed': parts[12] if len(parts) > 12 else 'N/A',
                        'clocks_sm': parts[13] if len(parts) > 13 else 'N/A',
                        'uuid': parts[14] if len(parts) > 14 else 'N/A',
                        'node': 'localhost'
                    })
        return gpus
    
    # No local nvidia-smi, try to get from compute nodes
    gpu_nodes = get_gpu_nodes()
    all_gpus = []
    
    for node_info in gpu_nodes:
        node_name = node_info['name']
        node_gpus = parse_nvidia_smi_from_node(node_name)
        if node_gpus:
            all_gpus.extend(node_gpus)
    
    return all_gpus


def collect_gpu_from_node(node_name):
    """并发采集单个节点的GPU信息"""
    try:
        return parse_nvidia_smi_from_node(node_name)
    except Exception as e:
        return []


def collect_gpu_processes_from_node(node_name):
    """并发采集单个节点的GPU进程信息"""
    try:
        return parse_nvidia_smi_processes_from_node(node_name)
    except Exception as e:
        return []


def collect_all_gpus_concurrent():
    """并发获取所有GPU节点的信息"""
    if has_local_nvidia_smi():
        return parse_nvidia_smi()
    
    gpu_nodes = get_gpu_nodes()
    if not gpu_nodes:
        return []
    
    all_gpus = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(collect_gpu_from_node, node['name']): node['name'] for node in gpu_nodes}
        for future in as_completed(futures, timeout=30):
            try:
                result = future.result()
                if result:
                    all_gpus.extend(result)
            except Exception:
                pass
    
    return all_gpus


def collect_all_gpu_processes_concurrent():
    """并发获取所有GPU节点的进程信息"""
    if has_local_nvidia_smi():
        return parse_nvidia_smi_processes()
    
    gpu_nodes = get_gpu_nodes()
    if not gpu_nodes:
        return []
    
    all_processes = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(collect_gpu_processes_from_node, node['name']): node['name'] for node in gpu_nodes}
        for future in as_completed(futures, timeout=30):
            try:
                result = future.result()
                if result:
                    all_processes.extend(result)
            except Exception:
                pass
    
    return all_processes


class GPUCache:
    """GPU信息缓存类"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._gpus = []
        self._gpu_processes = []
        self._timestamp = None
        self._cache_lock = threading.Lock()
        self._initialized = True
    
    def get_gpus(self):
        with self._cache_lock:
            return self._gpus
    
    def get_gpu_processes(self):
        with self._cache_lock:
            return self._gpu_processes
    
    def get_timestamp(self):
        with self._cache_lock:
            return self._timestamp
    
    def refresh(self):
        """刷新缓存"""
        gpus = collect_all_gpus_concurrent()
        processes = collect_all_gpu_processes_concurrent()
        with self._cache_lock:
            self._gpus = gpus
            self._gpu_processes = processes
            self._timestamp = datetime.datetime.now()


gpu_cache = GPUCache()


class GPUCacheUpdater(threading.Thread):
    """后台GPU缓存更新线程"""
    
    def __init__(self, interval=10):
        super().__init__()
        self.interval = interval
        self.running = False
    
    def run(self):
        self.running = True
        gpu_cache.refresh()
        while self.running:
            time.sleep(self.interval)
            try:
                gpu_cache.refresh()
            except Exception:
                pass
    
    def stop(self):
        self.running = False

def parse_nvidia_smi_processes_from_node(node_name):
    """Get GPU process information from a specific node via SSH"""
    processes = []
    
    # Try pmon first
    output = run_ssh_command(node_name, "nvidia-smi pmon -s um -c 1 2>/dev/null")
    if output and not output.startswith("Error") and "command not found" not in output.lower():
        lines = output.strip().split('\n')
        for line in lines:
            # Skip header lines starting with #
            if line.strip().startswith('#') or 'gpu' in line.lower():
                continue
            parts = line.split()
            # pmon format: gpu_idx pid type sm mem enc dec jpg ofa fb ccpm command
            if len(parts) >= 4:
                processes.append({
                    'gpu_id': parts[0],
                    'pid': parts[1],
                    'type': parts[2],
                    'sm': parts[3] if parts[3] != '-' else '0',
                    'mem': parts[4] if len(parts) > 4 and parts[4] != '-' else '0',
                    'enc': parts[5] if len(parts) > 5 and parts[5] != '-' else '0',
                    'dec': parts[6] if len(parts) > 6 and parts[6] != '-' else '0',
                    'command': ' '.join(parts[12:]) if len(parts) > 12 else ' '.join(parts[3:]),
                    'node': node_name
                })
    
    # Also try compute-apps query
    output2 = run_ssh_command(
        node_name,
        "nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits 2>/dev/null"
    )
    if output2 and not output2.startswith("Error") and "command not found" not in output2.lower():
        for line in output2.strip().split('\n'):
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 3:
                # Check if this pid is already in processes
                pid = parts[0]
                if not any(p['pid'] == pid and p.get('node') == node_name for p in processes):
                    processes.append({
                        'gpu_id': '0',
                        'pid': pid,
                        'type': 'C',
                        'sm': 'N/A',
                        'mem': parts[2],
                        'enc': '0',
                        'dec': '0',
                        'command': parts[1],
                        'node': node_name
                    })
    
    return processes


def parse_nvidia_smi_processes():
    """Get GPU process information
    
    If local nvidia-smi is available, use it.
    Otherwise, SSH to compute nodes with GPUs to get information.
    """
    # First, try local nvidia-smi
    if has_local_nvidia_smi():
        # Try pmon first
        output = run_command("nvidia-smi pmon -s um -c 1 2>/dev/null")
        processes = []
        if output and not output.startswith("Error"):
            lines = output.strip().split('\n')
            for line in lines:
                # Skip header lines starting with #
                if line.strip().startswith('#') or 'gpu' in line.lower():
                    continue
                parts = line.split()
                # pmon format: gpu_idx pid type sm mem enc dec jpg ofa fb ccpm command
                if len(parts) >= 4:
                    processes.append({
                        'gpu_id': parts[0],
                        'pid': parts[1],
                        'type': parts[2],
                        'sm': parts[3] if parts[3] != '-' else '0',
                        'mem': parts[4] if len(parts) > 4 and parts[4] != '-' else '0',
                        'enc': parts[5] if len(parts) > 5 and parts[5] != '-' else '0',
                        'dec': parts[6] if len(parts) > 6 and parts[6] != '-' else '0',
                        'command': ' '.join(parts[12:]) if len(parts) > 12 else ' '.join(parts[3:]),
                        'node': 'localhost'
                    })
        
        # Also try compute-apps query
        output2 = run_command("nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits 2>/dev/null")
        if output2 and not output2.startswith("Error"):
            for line in output2.strip().split('\n'):
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 3:
                    # Check if this pid is already in processes
                    pid = parts[0]
                    if not any(p['pid'] == pid for p in processes):
                        processes.append({
                            'gpu_id': '0',
                            'pid': pid,
                            'type': 'C',
                            'sm': 'N/A',
                            'mem': parts[2],
                            'enc': '0',
                            'dec': '0',
                            'command': parts[1],
                            'node': 'localhost'
                        })
        
        return processes
    
    # No local nvidia-smi, try to get from compute nodes
    gpu_nodes = get_gpu_nodes()
    all_processes = []
    
    for node_info in gpu_nodes:
        node_name = node_info['name']
        node_processes = parse_nvidia_smi_processes_from_node(node_name)
        if node_processes:
            all_processes.extend(node_processes)
    
    return all_processes

def parse_slurm_conf():
    """Parse slurm.conf for configuration"""
    conf_path = '/etc/slurm/slurm.conf'
    config = {'nodes': [], 'partitions': [], 'settings': {}}
    
    try:
        with open(conf_path, 'r') as f:
            content = f.read()
            
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                if line.startswith('NodeName='):
                    # Parse node definition
                    node_info = {}
                    for match in re.finditer(r'(\w+)=([^\s]+)', line):
                        key, value = match.groups()
                        node_info[key.lower()] = value
                    config['nodes'].append(node_info)
                elif line.startswith('PartitionName='):
                    # Parse partition definition
                    part_info = {}
                    for match in re.finditer(r'(\w+)=([^\s]+)', line):
                        key, value = match.groups()
                        part_info[key.lower()] = value
                    config['partitions'].append(part_info)
                elif '=' in line:
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        config['settings'][parts[0].strip()] = parts[1].strip()
    except Exception as e:
        config['error'] = str(e)
    
    return config

def get_user_stats():
    """Get statistics per user"""
    output = run_command("squeue -o '%u|%T|%C' -h")
    stats = defaultdict(lambda: {'running': 0, 'pending': 0, 'suspended': 0, 'cpus': 0, 'jobs': 0})
    
    if output and not output.startswith("Error"):
        for line in output.split('\n'):
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 3:
                    user, state, cpus = parts
                    stats[user]['jobs'] += 1
                    stats[user]['cpus'] += int(cpus) if cpus.isdigit() else 0
                    state_upper = state.upper()
                    if state_upper in ['R', 'RUNNING']:
                        stats[user]['running'] += 1
                    elif state_upper in ['PD', 'PENDING']:
                        stats[user]['pending'] += 1
                    elif state_upper in ['S', 'ST', 'SUSPENDED', 'STOPPED']:
                        stats[user]['suspended'] += 1
    
    return dict(stats)

def get_job_stats_by_partition():
    """Get job statistics grouped by partition"""
    output = run_command("squeue -o '%P|%T' -h")
    stats = defaultdict(lambda: {'running': 0, 'pending': 0, 'total': 0})
    
    if output and not output.startswith("Error"):
        for line in output.split('\n'):
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 2:
                    partition, state = parts
                    stats[partition]['total'] += 1
                    state_upper = state.upper()
                    if state_upper in ['R', 'RUNNING']:
                        stats[partition]['running'] += 1
                    elif state_upper in ['PD', 'PENDING']:
                        stats[partition]['pending'] += 1
    
    return dict(stats)

def get_cluster_summary():
    """Get overall cluster summary"""
    summary = {
        'nodes': {'total': 0, 'alloc': 0, 'idle': 0, 'down': 0, 'mix': 0},
        'jobs': {'running': 0, 'pending': 0, 'suspended': 0, 'total': 0},
        'cpus': {'total': 0, 'alloc': 0, 'idle': 0},
        'memory': {'total': 0, 'alloc': 0, 'free': 0},
        'gpus': {'total': 0, 'alloc': 0, 'utilized': 0}
    }
    
    # Get node info
    nodes = parse_sinfo()
    for node in nodes:
        summary['nodes']['total'] += 1
        state = node['state'].lower()
        if 'alloc' in state:
            summary['nodes']['alloc'] += 1
        elif 'idle' in state:
            summary['nodes']['idle'] += 1
        elif 'down' in state or 'drain' in state or 'fail' in state:
            summary['nodes']['down'] += 1
        elif 'mix' in state:
            summary['nodes']['mix'] += 1
        
        # CPU allocation format: Alloc/Idle/Other/Total
        cpu_alloc = node.get('cpu_alloc', '0/0/0/0').split('/')
        if len(cpu_alloc) == 4:
            summary['cpus']['alloc'] += int(cpu_alloc[0])
            summary['cpus']['idle'] += int(cpu_alloc[1])
            summary['cpus']['total'] += int(cpu_alloc[3])
        
        # Memory
        if node['memory'].isdigit():
            summary['memory']['total'] += int(node['memory'])
        if node['free_mem'].isdigit():
            summary['memory']['free'] += int(node['free_mem'])
    
    # Get job info
    jobs = parse_squeue()
    for job in jobs:
        summary['jobs']['total'] += 1
        state = job['state']
        if state == 'R':
            summary['jobs']['running'] += 1
        elif state == 'PD':
            summary['jobs']['pending'] += 1
        elif state in ['S', 'ST']:
            summary['jobs']['suspended'] += 1
    
    # Get GPU count from slurm config (via sinfo gres)
    nodes = parse_sinfo()
    total_gpus = 0
    for node in nodes:
        gres = node.get('gres', 'none')
        if 'gpu' in gres.lower():
            # Extract GPU count from gres like "gpu:4(S:0-1)" or "gpu:2"
            import re
            gpu_match = re.search(r'gpu:(\d+)', gres, re.IGNORECASE)
            if gpu_match:
                total_gpus += int(gpu_match.group(1))
    summary['gpus']['total'] = total_gpus
    
    # Check allocated GPUs from squeue
    for job in jobs:
        if job.get('gres') and 'gpu' in job['gres']:
            match = re.search(r'gpu:\d+', job['gres'])
            if match:
                num = int(match.group().split(':')[1])
                summary['gpus']['alloc'] += num
    
    return summary

def get_all_data():
    """Get all system data at once"""
    return {
        'summary': get_cluster_summary(),
        'nodes': parse_sinfo(),
        'jobs': parse_squeue(),
        'partitions': parse_partitions(),
        'gpus': gpu_cache.get_gpus(),
        'gpu_processes': gpu_cache.get_gpu_processes(),
        'user_stats': get_user_stats(),
        'partition_stats': get_job_stats_by_partition(),
        'config': parse_slurm_conf(),
        'timestamp': datetime.datetime.now().isoformat()
    }

# ============== Background Updater Thread ==============

class BackgroundUpdater:
    def __init__(self, interval=5):
        self.interval = interval
        self.running = False
        self.thread = None
    
    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run)
            self.thread.daemon = True
            self.thread.start()
    
    def stop(self):
        self.running = False
    
    def _run(self):
        while self.running:
            try:
                data = get_all_data()
                socketio.emit('data_update', data, namespace='/')
            except Exception as e:
                print(f"Background update error: {e}")
            time.sleep(self.interval)

updater = BackgroundUpdater(interval=5)

# ============== API Routes ==============

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/disk-quota')
def disk_quota_page():
    """Disk Quota management page"""
    return render_template('disk_quota.html')


@app.route('/file-manager')
def file_manager_page():
    """File Manager page"""
    if 'user_type' not in session:
        return redirect('/login')
    return render_template('file_manager.html')


@app.route('/api/files')
def api_list_files():
    """List files in user's home directory"""
    if 'user_type' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    username = session.get('username')
    user_type = session.get('user_type', 'user')
    request_path = request.args.get('path', '')
    
    if not username:
        return jsonify({'success': False, 'message': '无法获取用户信息'}), 400
    
    if user_type == 'admin':
        base_dir = '/home'
        if request_path:
            target_dir = os.path.join(base_dir, request_path)
        else:
            target_dir = base_dir
        
        target_dir = os.path.abspath(target_dir)
        if not target_dir.startswith(base_dir):
            return jsonify({'success': False, 'message': '路径超出范围'}), 403
    else:
        base_dir = os.path.join('/home', username)
        if request_path:
            target_dir = os.path.join(base_dir, request_path)
        else:
            target_dir = base_dir
        
        target_dir = os.path.abspath(target_dir)
        if not target_dir.startswith(base_dir):
            return jsonify({'success': False, 'message': '路径超出用户目录范围'}), 403
    
    if not os.path.exists(target_dir):
        return jsonify({'success': False, 'message': '目录不存在'}), 404
    
    if not os.path.isdir(target_dir):
        return jsonify({'success': False, 'message': '路径不是目录'}), 400
    
    try:
        files = []
        items = sorted(os.listdir(target_dir), key=lambda x: (not os.path.isdir(os.path.join(target_dir, x)), x.lower()))
        
        for item in items:
            item_path = os.path.join(target_dir, item)
            stat = os.stat(item_path)
            
            files.append({
                'name': item,
                'is_dir': os.path.isdir(item_path),
                'size': stat.st_size,
                'modified': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                'path': os.path.relpath(item_path, base_dir)
            })
        
        current_path = request_path if request_path else ''
        parent_path = os.path.dirname(current_path) if current_path else None
        
        return jsonify({
            'success': True,
            'files': files,
            'current_path': current_path,
            'parent_path': parent_path,
            'base_dir': base_dir,
            'user_type': user_type
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/files/delete', methods=['POST'])
def api_delete_file():
    """Delete file or directory"""
    if 'user_type' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    username = session.get('username')
    user_type = session.get('user_type', 'user')
    data = request.json
    file_path = data.get('path', '')
    base_dir = data.get('base_dir', '')
    
    if not username or not file_path:
        return jsonify({'success': False, 'message': '参数不完整'}), 400
    
    if user_type == 'admin' and base_dir:
        user_home = '/home'
    else:
        user_home = os.path.join('/home', username)
    
    target_path = os.path.join(user_home, file_path)
    target_path = os.path.abspath(target_path)
    
    if not target_path.startswith(user_home):
        return jsonify({'success': False, 'message': '路径超出用户目录范围'}), 403
    
    if not os.path.exists(target_path):
        return jsonify({'success': False, 'message': '文件不存在'}), 404
    
    try:
        if os.path.isdir(target_path):
            shutil.rmtree(target_path)
        else:
            os.remove(target_path)
        return jsonify({'success': True, 'message': '删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/files/upload', methods=['POST'])
def api_upload_file():
    """Upload file to user's home directory"""
    if 'user_type' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    username = session.get('username')
    user_type = session.get('user_type', 'user')
    target_path = request.form.get('path', '')
    base_dir = request.form.get('base_dir', '')
    
    if not username:
        return jsonify({'success': False, 'message': '无法获取用户信息'}), 400
    
    if user_type == 'admin' and base_dir:
        user_home = '/home'
    else:
        user_home = os.path.join('/home', username)
    
    upload_dir = os.path.join(user_home, target_path) if target_path else user_home
    upload_dir = os.path.abspath(upload_dir)
    
    if not upload_dir.startswith(user_home):
        return jsonify({'success': False, 'message': '路径超出用户目录范围'}), 403
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '文件名不能为空'}), 400
    
    try:
        file_path = os.path.join(upload_dir, file.filename)
        file.save(file_path)
        return jsonify({'success': True, 'message': '上传成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/files/download')
def api_download_file():
    """Download file from user's home directory"""
    if 'user_type' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    username = session.get('username')
    user_type = session.get('user_type', 'user')
    file_path = request.args.get('path', '')
    base_dir = request.args.get('base_dir', '')
    
    if not username or not file_path:
        return jsonify({'success': False, 'message': '参数不完整'}), 400
    
    if user_type == 'admin' and base_dir:
        user_home = '/home'
    else:
        user_home = os.path.join('/home', username)
    
    target_path = os.path.join(user_home, file_path)
    target_path = os.path.abspath(target_path)
    
    if not target_path.startswith(user_home):
        return jsonify({'success': False, 'message': '路径超出用户目录范围'}), 403
    
    if not os.path.exists(target_path):
        return jsonify({'success': False, 'message': '文件不存在'}), 404
    
    if os.path.isdir(target_path):
        return jsonify({'success': False, 'message': '不能下载目录'}), 400
    
    try:
        return flask_send_file(target_path, as_attachment=True)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/files/view')
def api_view_file():
    """View file content"""
    if 'user_type' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    username = session.get('username')
    user_type = session.get('user_type', 'user')
    file_path = request.args.get('path', '')
    base_dir = request.args.get('base_dir', '')
    
    if not username or not file_path:
        return jsonify({'success': False, 'message': '参数不完整'}), 400
    
    if user_type == 'admin' and base_dir:
        user_home = '/home'
    else:
        user_home = os.path.join('/home', username)
    
    target_path = os.path.join(user_home, file_path)
    target_path = os.path.abspath(target_path)
    
    if not target_path.startswith(user_home):
        return jsonify({'success': False, 'message': '路径超出用户目录范围'}), 403
    
    if not os.path.exists(target_path):
        return jsonify({'success': False, 'message': '文件不存在'}), 404
    
    if os.path.isdir(target_path):
        return jsonify({'success': False, 'message': '不能查看目录'}), 400
    
    file_size = os.path.getsize(target_path)
    if file_size > 1024 * 1024:
        return jsonify({'success': False, 'message': '文件太大，无法预览（最大1MB）'}), 400
    
    try:
        with open(target_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return jsonify({'success': True, 'content': content, 'name': os.path.basename(target_path)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/terminal')
def terminal_page():
    """Terminal page for SSH to nodes"""
    node = request.args.get('node', '')
    return render_template('terminal.html', node=node)


@app.route('/api/terminal/exec', methods=['POST'])
def api_terminal_exec():
    """Execute command on remote node via SSH"""
    if 'user_type' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403
    
    data = request.json
    node = data.get('node', '')
    command = data.get('command', '')
    
    if not node:
        return jsonify({'success': False, 'message': '未指定节点'}), 400
    
    ssh_cmd = f"ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no {node} {command}"
    result = run_command(ssh_cmd, timeout=30)
    
    return jsonify({'success': True, 'output': result})


@app.route('/api/disk-quota')
def api_disk_quota():
    """Get disk quota information"""
    quota_data = parse_disk_quota()
    return jsonify(quota_data)

@app.route('/api/disk-quota/set', methods=['POST'])
def api_set_disk_quota():
    """Set user disk quota"""
    # 检查是否管理员
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'message': '只有管理员才能设置配额'}), 403
    
    data = request.json
    username = data.get('username', '').strip()
    soft_limit = data.get('soft_limit', '0')
    hard_limit = data.get('hard_limit', '0')
    soft_files = data.get('soft_files', '0')
    hard_files = data.get('hard_files', '0')
    
    if not username:
        return jsonify({'success': False, 'message': '请输入用户名'})
    
    # 转换容量单位为KB
    def to_kb(value, unit):
        try:
            num = float(value)
        except:
            num = 0
        if unit == 'T':
            return int(num * 1024 * 1024)
        elif unit == 'G':
            return int(num * 1024)
        elif unit == 'M':
            return int(num * 1024)
        elif unit == 'K':
            return int(num)
        return 0
    
    # 解析软限制和硬限制
    soft_unit = 'G'
    hard_unit = 'G'
    
    if soft_limit and isinstance(soft_limit, str):
        for u in ['T', 'G', 'M', 'K']:
            if u in soft_limit:
                soft_unit = u
                soft_limit = soft_limit.replace(u, '')
                break
    
    if hard_limit and isinstance(hard_limit, str):
        for u in ['T', 'G', 'M', 'K']:
            if u in hard_limit:
                hard_unit = u
                hard_limit = hard_limit.replace(u, '')
                break
    
    try:
        soft_kb = to_kb(soft_limit or '0', soft_unit)
        hard_kb = to_kb(hard_limit or '0', hard_unit)
    except:
        soft_kb = 0
        hard_kb = 0
    
    # setquota -u username block_soft block_hard inode_soft inode_hard -a
    cmd = f'setquota -u {username} {soft_kb} {hard_kb} {soft_files or 0} {hard_files or 0} -a'
    
    result = run_command(cmd)
    
    if result is not None and not result.startswith("Error"):
        return jsonify({'success': True, 'message': '配额设置成功'})
    else:
        return jsonify({'success': False, 'message': result or '设置失败'})

@app.route('/resource-quotas')
def resource_quotas_page():
    """Resource Quota management page"""
    return render_template('resource_quotas.html')

@app.route('/qos')
def qos_page():
    """QOS management page"""
    return render_template('qos.html')

@app.route('/accounts')
def accounts_page():
    """Account and user management page"""
    return render_template('accounts.html')

@app.route('/topology')
def topology_page():
    """Organization topology page"""
    return render_template('topology.html')

@app.route('/api/summary')
def api_summary():
    return jsonify(get_cluster_summary())

@app.route('/api/nodes')
def api_nodes():
    return jsonify(parse_sinfo())

@app.route('/api/node/<node_name>')
def api_node_detail(node_name):
    return jsonify(parse_node_details(node_name))

def get_user_jobs(username):
    """获取指定用户的所有作业"""
    output = run_command(f"squeue -u {username} -o %i")
    if output and not output.startswith("Error"):
        job_ids = []
        for line in output.strip().split('\n'):
            if line.isdigit():
                job_ids.append(line)
        return job_ids
    return []

@app.route('/api/jobs/batch', methods=['POST'])
def api_batch_job_action():
    """Perform batch action on jobs (cancel, hold, release, suspend, resume)"""
    # 检查登录
    if 'user_type' not in session:
        return jsonify({'success': False, 'message': '请先登录'}), 401
    
    current_user = session.get('username')
    user_type = session.get('user_type')
    
    data = request.json or {}
    job_ids = data.get('job_ids', [])
    action = data.get('action', '')  # 'cancel', 'hold', 'release', 'suspend', 'resume'
    
    if not job_ids:
        return jsonify({'success': False, 'message': '未选择作业'}), 400
    
    # 普通用户只能操作自己的作业
    if user_type != 'admin':
        # 获取当前用户的作业
        user_job_ids = set(get_user_jobs(current_user))
        # 过滤只保留当前用户的作业
        job_ids = [jid for jid in job_ids if str(jid) in user_job_ids]
        if not job_ids:
            return jsonify({'success': False, 'message': '只能操作自己的作业'}), 403
    
    job_list = ' '.join(map(str, job_ids))
    
    if action == 'cancel':
        result = run_command(f"scancel {job_list}")
    elif action == 'hold':
        result = run_command(f"scontrol hold {job_list}")
    elif action == 'release':
        result = run_command(f"scontrol release {job_list}")
    elif action == 'suspend':
        result = run_command(f"scontrol suspend {job_list}")
    elif action == 'resume':
        result = run_command(f"scontrol resume {job_list}")
    else:
        return jsonify({'success': False, 'message': '无效的操作'}), 400
    
    if not result or not result.startswith("Error"):
        return jsonify({'success': True, 'message': f'批量操作成功: {action}'})
    else:
        return jsonify({'success': False, 'message': result}), 500

@app.route('/api/jobs')
def api_jobs():
    return jsonify(parse_squeue())

@app.route('/api/job/<job_id>')
def api_job_detail(job_id):
    """Get detailed job information using scontrol and sacct (like jobinfo script)"""
    details = {}
    
    # 1. First try scontrol for running/pending jobs
    output = run_command(f"scontrol show job {job_id}")
    if output and not output.startswith("Error"):
        for line in output.split('\n'):
            for match in re.finditer(r'(\w+)=([^\s]+)', line):
                key, value = match.groups()
                details[key.lower()] = value
    
    # 2. Use sacct to get detailed information (like jobinfo script)
    # Format similar to jobinfo: JobName,JobID,User,Account,Partition,QOS,NodeList,ReqTRES,State,ExitCode,
    # Submit,Start,End,Reserved,Timelimit,Elapsed,TotalCPU,SystemCPU,UserCPU,ReqMem,MaxRSS,MaxDiskWrite,MaxDiskRead,WorkDir,SubmitLine
    sacct_output = run_command(
        f"sacct -j {job_id} --format=JobName,JobID,JobIDRaw,User,Account,Partition,QOS,NodeList,ReqTRES,State,ExitCode,"
        f"Submit,Start,End,Reserved,Timelimit,Elapsed,TotalCPU,SystemCPU,UserCPU,ReqMem,MaxRSS,MaxDiskWrite,MaxDiskRead,WorkDir,SubmitLine "
        f"--parsable2 --noheader 2>/dev/null"
    )
    
    if sacct_output and not sacct_output.startswith("Error"):
        lines = sacct_output.strip().split('\n')
        for line in lines:
            parts = line.split('|')
            if len(parts) >= 25:
                # Skip .extern steps, use the main job or batch step
                job_id_raw = parts[1] if len(parts) > 1 else ''
                if '.extern' in job_id_raw:
                    continue
                    
                # Parse sacct fields
                sacct_data = {
                    'jobname': parts[0],
                    'jobid': parts[1],
                    'jobidraw': parts[2],
                    'userid': parts[3],
                    'account': parts[4],
                    'partition': parts[5],
                    'qos': parts[6],
                    'nodelist': parts[7],
                    'reqtres': parts[8],
                    'state': parts[9],
                    'exitcode': parts[10],
                    'submittime': parts[11],
                    'starttime': parts[12],
                    'endtime': parts[13],
                    'reserved': parts[14],  # Waited time
                    'timelimit': parts[15],
                    'elapsed': parts[16],
                    'totalcpu': parts[17],
                    'systemcpu': parts[18],
                    'usercpu': parts[19],
                    'reqmem': parts[20],
                    'maxrss': parts[21],
                    'maxdiskwrite': parts[22],
                    'maxdiskread': parts[23],
                    'workdir': parts[24],
                    'submitline': parts[25] if len(parts) > 25 else ''
                }
                
                # Merge with scontrol data (sacct takes precedence for overlapping fields)
                for key, value in sacct_data.items():
                    if value and value not in ['', 'None', 'null']:
                        details[key] = value
                
                # Calculate additional metrics
                # Extract GPU count from ReqTRES
                reqtres = sacct_data.get('reqtres', '')
                if reqtres and 'gpu' in reqtres.lower():
                    gpu_match = re.search(r'gres/gpu=(\d+)', reqtres, re.IGNORECASE)
                    if gpu_match:
                        details['gpus'] = gpu_match.group(1)
                    else:
                        details['gpus'] = '0'
                else:
                    details['gpus'] = details.get('gpus', '0')
                
                # Calculate CPU utilization percentage
                totalcpu = sacct_data.get('totalcpu', '')
                elapsed = sacct_data.get('elapsed', '')
                if totalcpu and elapsed and ':' in totalcpu and ':' in elapsed:
                    try:
                        # Convert time strings to seconds
                        def time_to_seconds(t):
                            parts = t.split(':')
                            if len(parts) == 3:
                                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                            elif len(parts) == 2:
                                return int(parts[0]) * 60 + float(parts[1])
                            return 0
                        
                        totalcpu_sec = time_to_seconds(totalcpu)
                        elapsed_sec = time_to_seconds(elapsed)
                        numcpus = float(details.get('numcpus', details.get('reqcpus', '1')))
                        
                        if elapsed_sec > 0 and numcpus > 0:
                            cpu_eff = (totalcpu_sec / (elapsed_sec * numcpus)) * 100
                            details['cpu_efficiency'] = f"{cpu_eff:.2f}%"
                    except:
                        pass
                
                # Calculate memory utilization
                maxrss = sacct_data.get('maxrss', '')
                reqmem = sacct_data.get('reqmem', '')
                if maxrss and reqmem:
                    try:
                        # Parse memory values (handle K, M, G, T suffixes)
                        def parse_mem(val):
                            val = val.strip()
                            if not val or val == '':
                                return 0
                            units = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
                            unit = val[-1].upper() if val[-1].upper() in units else ''
                            num = float(val[:-1]) if unit else float(val)
                            return num * units.get(unit, 1)
                        
                        maxrss_bytes = parse_mem(maxrss)
                        reqmem_bytes = parse_mem(reqmem)
                        
                        if reqmem_bytes > 0:
                            mem_eff = (maxrss_bytes / reqmem_bytes) * 100
                            details['mem_efficiency'] = f"{mem_eff:.2f}%"
                            details['maxrss_formatted'] = format_bytes(maxrss_bytes)
                    except:
                        pass
                
                break  # Use first matching line (main job step)
    
    # 3. For running jobs, try to get real-time stats from sstat
    state = details.get('state', '').upper()
    if 'RUNNING' in state or 'R' in state:
        sstat_output = run_command(
            f"sstat -j {job_id} --format=JobID,MaxRSS,MaxDiskWrite,MaxDiskRead --parsable2 --noheader 2>/dev/null"
        )
        if sstat_output and not sstat_output.startswith("Error"):
            lines = sstat_output.strip().split('\n')
            for line in lines:
                parts = line.split('|')
                if len(parts) >= 4:
                    if parts[1]:  # MaxRSS
                        details['maxrss_live'] = parts[1]
                    if parts[2]:  # MaxDiskWrite
                        details['maxdiskwrite_live'] = parts[2]
                    if parts[3]:  # MaxDiskRead
                        details['maxdiskread_live'] = parts[3]
                    break
    
    # 4. For pending jobs, get reason from squeue
    if 'PENDING' in state or 'PD' in state:
        squeue_output = run_command(
            f"squeue -j {job_id} --format=%E;%R --noheader 2>/dev/null"
        )
        if squeue_output and not squeue_output.startswith("Error"):
            parts = squeue_output.strip().split(';')
            if len(parts) >= 2:
                details['dependency'] = parts[0] if parts[0] else ''
                details['reason'] = parts[1] if parts[1] else ''
    
    return jsonify(details)


def format_bytes(bytes_val):
    """Convert bytes to human readable format"""
    if bytes_val <= 0:
        return "0B"
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    unit_index = 0
    while bytes_val >= 1024 and unit_index < len(units) - 1:
        bytes_val /= 1024
        unit_index += 1
    return f"{bytes_val:.2f}{units[unit_index]}"


@app.route('/api/jobs/history')
def api_jobs_history():
    """Get historical jobs from past 30 days with pagination (like jobinfo)
    
    Query params:
        days: Number of days to look back (default: 30, max: 90)
        page: Page number (default: 1)
        per_page: Items per page (default: 50, max: 100)
        state: Filter by state (optional)
        user: Filter by user (optional)
        partition: Filter by partition (optional)
    """
    days = request.args.get('days', 30, type=int)
    days = min(max(days, 1), 90)  # Limit to 1-90 days
    
    page = request.args.get('page', 1, type=int)
    page = max(page, 1)
    
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(max(per_page, 10), 100)  # Limit to 10-100 items per page
    
    state_filter = request.args.get('state', '')
    user_filter = request.args.get('user', '')
    partition_filter = request.args.get('partition', '')
    
    # Use sacct to get historical jobs - similar to jobinfo fields
    # Note: Remove -X flag to get MaxRSS/MaxDiskWrite/MaxDiskRead from batch step
    # Fields: JobID, JobName, User, Account, Partition, State, ExitCode, 
    #         Submit, Start, End, Elapsed, Timelimit, ReqCPUS, ReqMem, 
    #         ReqTRES, MaxRSS, MaxDiskWrite, MaxDiskRead, TotalCPU, NNodes
    output = run_command(
        f"sacct -S now-{days}days --format="
        f"JobID,JobName,User,Account,Partition,State,ExitCode,"
        f"Submit,Start,End,Elapsed,Timelimit,ReqCPUS,ReqMem,"
        f"ReqTRES,MaxRSS,MaxDiskWrite,MaxDiskRead,TotalCPU,NNodes "
        f"--parsable2 --noheader 2>/dev/null"
    )
    
    # Parse sacct output and merge data from main job and batch steps
    jobs_dict = {}  # Use dict to group by job_id
    
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split('|')
            if len(parts) >= 20:
                full_job_id = parts[0]
                # Skip .extern steps
                if '.extern' in full_job_id:
                    continue
                
                # Extract base job_id (remove .batch suffix)
                if '.batch' in full_job_id:
                    job_id = full_job_id.replace('.batch', '')
                    is_batch = True
                else:
                    job_id = full_job_id
                    is_batch = False
                
                # Initialize job entry if not exists
                if job_id not in jobs_dict:
                    jobs_dict[job_id] = {}
                
                job_entry = jobs_dict[job_id]
                
                if is_batch:
                    # Batch step contains resource usage data
                    job_entry['maxrss'] = parts[15] if parts[15] else '-'
                    job_entry['maxdiskwrite'] = parts[16] if parts[16] else '-'
                    job_entry['maxdiskread'] = parts[17] if parts[17] else '-'
                    job_entry['totalcpu'] = parts[18] if parts[18] else '-'
                else:
                    # Main job contains basic info
                    job_entry['job_id'] = job_id
                    job_entry['name'] = parts[1]
                    job_entry['user'] = parts[2]
                    job_entry['account'] = parts[3] if parts[3] else '-'
                    job_entry['partition'] = parts[4]
                    job_entry['state'] = parts[5]
                    job_entry['exitcode'] = parts[6] if parts[6] else '-'
                    job_entry['submit_time'] = parts[7]
                    job_entry['start_time'] = parts[8] if parts[8] else '-'
                    job_entry['end_time'] = parts[9] if parts[9] else '-'
                    job_entry['elapsed'] = parts[10] if parts[10] else '-'
                    job_entry['timelimit'] = parts[11] if parts[11] else '-'
                    job_entry['cpus'] = parts[12] if parts[12] else '-'
                    job_entry['reqmem'] = parts[13] if parts[13] else '-'
                    job_entry['reqtres'] = parts[14] if parts[14] else ''
                    job_entry['nodes'] = parts[19] if parts[19] else '1'
                    
                    # Also try to get resource usage from main job if batch step not available
                    if 'maxrss' not in job_entry:
                        job_entry['maxrss'] = parts[15] if parts[15] else '-'
                        job_entry['maxdiskwrite'] = parts[16] if parts[16] else '-'
                        job_entry['maxdiskread'] = parts[17] if parts[17] else '-'
                        job_entry['totalcpu'] = parts[18] if parts[18] else '-'
    
    # Convert dict to list and add default values
    jobs = []
    for job_id, job in jobs_dict.items():
        # Ensure all required fields exist
        job.setdefault('maxrss', '-')
        job.setdefault('maxdiskwrite', '-')
        job.setdefault('maxdiskread', '-')
        job.setdefault('totalcpu', '-')
        
        # Extract GPU count from ReqTRES
        reqtres = job.get('reqtres', '')
        if reqtres and 'gpu' in reqtres.lower():
            gpu_match = re.search(r'gres/gpu=(\d+)', reqtres, re.IGNORECASE)
            job['gpus'] = gpu_match.group(1) if gpu_match else '0'
        else:
            job['gpus'] = '0'
        
        # Apply filters
        if state_filter and job.get('state') != state_filter:
            continue
        if user_filter and job.get('user') != user_filter:
            continue
        if partition_filter and job.get('partition') != partition_filter:
            continue
        
        jobs.append(job)
    
    # Sort by submit time descending (newest first)
    jobs.sort(key=lambda x: x['submit_time'], reverse=True)
    
    # Pagination
    total = len(jobs)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    
    # Ensure page is within bounds
    if page > total_pages:
        page = total_pages
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_jobs = jobs[start_idx:end_idx]
    
    return jsonify({
        'jobs': paginated_jobs,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1
        }
    })


@app.route('/api/priority')
def api_priority():
    """Get job priority details from sprio"""
    output = run_command('sprio -o "%i|%Q|%a|%A|%F|%J|%P|%q|%n|%T"')
    priorities = []
    if output and not output.startswith("Error"):
        lines = output.strip().split('\n')[1:]  # Skip header
        for line in lines:
            parts = line.split('|')
            if len(parts) >= 9:
                priorities.append({
                    'job_id': parts[0],
                    'priority': parts[1],
                    'age_raw': parts[2],      # 原始 AGE 值
                    'age': parts[3],          # 调整后 AGE
                    'fairshare': parts[4],
                    'jobsize': parts[5],
                    'partition': parts[6],
                    'qos': parts[7],
                    'qos_name': parts[8],
                    'tres': parts[9] if len(parts) > 9 else ''
                })
    return jsonify(priorities)

@app.route('/api/partitions')
def api_partitions():
    return jsonify(parse_partitions())

@app.route('/api/history')
def api_history():
    hours = request.args.get('hours', 24, type=int)
    return jsonify(parse_sacct_history(hours))

@app.route('/api/diag')
def api_diag():
    return jsonify(parse_sdiag())

@app.route('/api/user-resource-usage')
def api_user_resource_usage():
    """Get CPU and GPU time per user"""
    hours = request.args.get('hours', 24, type=int)
    return jsonify(get_user_resource_usage(hours))

@app.route('/api/sreport')
def api_sreport():
    return jsonify(parse_sreport_cluster_usage())

@app.route('/api/gpus')
def api_gpus():
    gpus = gpu_cache.get_gpus()
    if not gpus:
        gpu_cache.refresh()
        gpus = gpu_cache.get_gpus()
    return jsonify(gpus)

@app.route('/api/gpus/refresh', methods=['POST'])
def api_gpus_refresh():
    gpu_cache.refresh()
    return jsonify({'success': True, 'timestamp': gpu_cache.get_timestamp()})

@app.route('/api/gpu-processes')
def api_gpu_processes():
    processes = gpu_cache.get_gpu_processes()
    if not processes:
        gpu_cache.refresh()
        processes = gpu_cache.get_gpu_processes()
    return jsonify(processes)

@app.route('/api/config')
def api_config():
    return jsonify(parse_slurm_conf())

@app.route('/api/user-stats')
def api_user_stats():
    return jsonify(get_user_stats())

@app.route('/api/partition-stats')
def api_partition_stats():
    return jsonify(get_job_stats_by_partition())

@app.route('/api/allsystems')
def api_all_systems():
    """Get all system data at once"""
    return jsonify(get_all_data())

# Job management actions
@app.route('/api/job/<job_id>/cancel', methods=['POST'])
def api_job_cancel(job_id):
    # 检查登录
    if 'user_type' not in session:
        return jsonify({'success': False, 'message': '请先登录'}), 401
    
    current_user = session.get('username')
    user_type = session.get('user_type')
    
    # 普通用户只能取消自己的作业
    if user_type != 'admin':
        user_job_ids = set(get_user_jobs(current_user))
        if str(job_id) not in user_job_ids:
            return jsonify({'success': False, 'message': '只能取消自己的作业'}), 403
    
    result = run_command(f"scancel {job_id}")
    return jsonify({'success': not result.startswith("Error"), 'message': result})

@app.route('/api/verify-password', methods=['POST'])
def api_verify_password():
    """Verify admin password"""
    config = load_config()
    if not config.get('password_enabled', True):
        return jsonify({'success': True})
    
    data = request.json or {}
    password = data.get('password', '')
    
    if password == config.get('admin_password', 'admin888'):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': '密码错误'}), 403

@app.route('/api/app-config', methods=['GET'])
def api_get_app_config():
    """Get app configuration (without password)"""
    config = load_config()
    return jsonify({
        'password_enabled': config.get('password_enabled', True)
    })

@app.route('/api/app-config', methods=['POST'])
def api_update_app_config():
    """Update app configuration"""
    data = request.json or {}
    config = load_config()
    
    # Verify current password if enabled (skip if admin session)
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        current_password = data.get('current_password', '')
        if current_password != config.get('admin_password', 'admin888'):
            return jsonify({'success': False, 'message': '当前密码错误'}), 403
    
    # Update password
    if 'new_password' in data:
        config['admin_password'] = data['new_password']
    
    # Update password enabled status
    if 'password_enabled' in data:
        config['password_enabled'] = data['password_enabled']
    
    save_config(config)
    return jsonify({'success': True, 'message': '配置已更新'})

# ============== 公告管理 ==============
@app.route('/api/announcements', methods=['GET'])
def api_get_announcements():
    """获取公告列表"""
    config = load_config()
    announcements = config.get('announcements', [])
    return jsonify({'success': True, 'announcements': announcements})

@app.route('/api/announcements', methods=['POST'])
def api_add_announcement():
    """添加公告（仅管理员）"""
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    data = request.json or {}
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()
    priority = data.get('priority', 'normal')
    
    if not title or not content:
        return jsonify({'success': False, 'message': '标题和内容不能为空'})
    
    config = load_config()
    announcements = config.get('announcements', [])
    
    new_id = max([a.get('id', 0) for a in announcements], default=0) + 1
    new_announcement = {
        'id': new_id,
        'title': title,
        'content': content,
        'priority': priority,
        'created_at': datetime.datetime.now().isoformat()
    }
    
    announcements.insert(0, new_announcement)
    config['announcements'] = announcements
    save_config(config)
    
    return jsonify({'success': True, 'announcement': new_announcement})

@app.route('/api/announcements/<int:announcement_id>', methods=['PUT'])
def api_update_announcement(announcement_id):
    """更新公告（仅管理员）"""
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    data = request.json or {}
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()
    priority = data.get('priority', 'normal')
    
    if not title or not content:
        return jsonify({'success': False, 'message': '标题和内容不能为空'})
    
    config = load_config()
    announcements = config.get('announcements', [])
    
    for announcement in announcements:
        if announcement.get('id') == announcement_id:
            announcement['title'] = title
            announcement['content'] = content
            announcement['priority'] = priority
            announcement['updated_at'] = datetime.datetime.now().isoformat()
            break
    else:
        return jsonify({'success': False, 'message': '公告不存在'})
    
    config['announcements'] = announcements
    save_config(config)
    
    return jsonify({'success': True})

@app.route('/api/announcements/<int:announcement_id>', methods=['DELETE'])
def api_delete_announcement(announcement_id):
    """删除公告（仅管理员）"""
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    config = load_config()
    announcements = config.get('announcements', [])
    
    announcements = [a for a in announcements if a.get('id') != announcement_id]
    config['announcements'] = announcements
    save_config(config)
    
    return jsonify({'success': True})


@app.route('/api/job/<job_id>/hold', methods=['POST'])
def api_job_hold(job_id):
    result = run_command(f"scontrol hold {job_id}")
    return jsonify({'success': not result.startswith("Error"), 'message': result})

@app.route('/api/job/<job_id>/release', methods=['POST'])
def api_job_release(job_id):
    result = run_command(f"scontrol release {job_id}")
    return jsonify({'success': not result.startswith("Error"), 'message': result})

# Node management
@app.route('/api/node/<node_name>/drain', methods=['POST'])
def api_node_drain(node_name):
    # Verify password - skip if admin logged in via session
    config = load_config()
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        data = request.json or {}
        if data.get('password') != config.get('admin_password', 'admin'):
            return jsonify({'success': False, 'message': '密码错误'}), 401
    
    reason = request.json.get('reason', 'maintenance') if request.json else 'maintenance'
    # URL decode node name and handle special characters
    from urllib.parse import unquote
    node_name = unquote(node_name)
    
    # Debug: print raw node name
    print(f"[DEBUG] Drain request for node: '{node_name}'")
    print(f"[DEBUG] Node name repr: {repr(node_name)}")
    
    # First, verify node exists
    verify = run_command(f'scontrol show node {node_name}')
    verify_short = verify[:100] if verify else 'None'
    print(f"[DEBUG] Verify node result: {verify_short}")
    
    if verify.startswith("Error"):
        return jsonify({'success': False, 'message': f'节点不存在或无法访问: {node_name}'})
    
    # Use scontrol update with proper syntax
    # Note: No quotes around node_name in scontrol command
    cmd = f'scontrol update nodename={node_name} state=drain reason={reason}'
    print(f"[DEBUG] Executing: {cmd}")
    result = run_command(cmd)
    print(f"[DEBUG] Result: {result}")
    
    return jsonify({'success': not result.startswith("Error"), 'message': result})

@app.route('/api/node/<node_name>/resume', methods=['POST'])
def api_node_resume(node_name):
    # Verify password - skip if admin logged in via session
    config = load_config()
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        data = request.json or {}
        if data.get('password') != config.get('admin_password', 'admin'):
            return jsonify({'success': False, 'message': '密码错误'}), 401
    
    # URL decode node name and handle special characters
    from urllib.parse import unquote
    node_name = unquote(node_name)
    
    print(f"[DEBUG] Resume request for node: '{node_name}'")
    print(f"[DEBUG] Node name repr: {repr(node_name)}")
    
    # First, verify node exists
    verify = run_command(f'scontrol show node {node_name}')
    verify_short2 = verify[:100] if verify else 'None'
    print(f"[DEBUG] Verify node result: {verify_short2}")
    
    if verify.startswith("Error"):
        return jsonify({'success': False, 'message': f'节点不存在或无法访问: {node_name}'})
    
    # Use scontrol update with proper syntax
    cmd = f'scontrol update nodename={node_name} state=resume'
    print(f"[DEBUG] Executing: {cmd}")
    result = run_command(cmd)
    print(f"[DEBUG] Result: {result}")
    
    return jsonify({'success': not result.startswith("Error"), 'message': result})

# ============== SocketIO Events ==============

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    emit('connected', {'status': 'connected', 'timestamp': datetime.datetime.now().isoformat()})
    # Send initial data immediately
    emit('data_update', get_all_data())

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    pass

@socketio.on('request_update')
def handle_update_request():
    """Handle explicit data update request"""
    emit('data_update', get_all_data())

@socketio.on('start_monitoring')
def handle_start_monitoring():
    """Start background monitoring"""
    updater.start()
    emit('monitoring_started', {'status': 'started'})

@socketio.on('stop_monitoring')
def handle_stop_monitoring():
    """Stop background monitoring"""
    updater.stop()
    emit('monitoring_stopped', {'status': 'stopped'})


terminal_sessions = {}


class SSHSession:
    """SSH 会话管理类"""
    def __init__(self, node):
        self.node = node
        self.ssh = None
        self.channel = None
        self.connected = False
        
    def connect(self, username=None):
        """建立 SSH 连接"""
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            connect_kwargs = {
                'hostname': self.node,
                'timeout': 10,
                'allow_agent': True,
                'look_for_keys': True
            }
            
            if username:
                connect_kwargs['username'] = username
            else:
                connect_kwargs['username'] = 'root'
            
            self.ssh.connect(**connect_kwargs)
            self.channel = self.ssh.invoke_shell(term='xterm-256color', width=80, height=24)
            self.connected = True
            return True
        except Exception as e:
            print(f"SSH 连接失败: {e}")
            return False
    
    def write(self, data):
        """发送数据到 SSH 通道"""
        print(f"SSH write: channel={self.channel is not None}, connected={self.connected}, data={repr(data)}")
        if self.channel and self.connected:
            try:
                self.channel.send(data)
                print("SSH write success")
            except Exception as e:
                print(f"SSH write error: {e}")
    
    def read(self, size=4096):
        """从 SSH 通道读取数据"""
        if self.channel and self.connected:
            try:
                if self.channel.recv_ready():
                    data = self.channel.recv(size).decode('utf-8', errors='ignore')
                    if data:
                        print(f"SSH read: {repr(data[:100])}")
                    return data
            except Exception as e:
                print(f"SSH read error: {e}")
        return ''
    
    def resize(self, width, height):
        """调整终端大小"""
        if self.channel and self.connected:
            try:
                self.channel.resize(width=width, height=height)
            except:
                pass
    
    def close(self):
        """关闭 SSH 连接"""
        try:
            if self.channel:
                self.channel.close()
            if self.ssh:
                self.ssh.close()
        except:
            pass
        self.connected = False


@socketio.on('terminal_connect')
def handle_terminal_connect(data):
    """处理终端连接请求"""
    if 'user_type' not in session:
        emit('terminal_error', {'message': '未登录'}, namespace='/')
        return
    
    if session.get('user_type') != 'admin':
        emit('terminal_error', {'message': '需要管理员权限'}, namespace='/')
        return
    
    node = data.get('node', '')
    if not node:
        emit('terminal_error', {'message': '未指定节点'}, namespace='/')
        return
    
    sid = request.sid
    
    ssh_session = SSHSession(node)
    if ssh_session.connect():
        terminal_sessions[sid] = ssh_session
        emit('terminal_connected', {'node': node}, namespace='/')
        
        # 使用 socketio 的 background task 替代 threading.Thread
        def read_output(sid, ssh_session, socketio):
            while sid in terminal_sessions:
                try:
                    data = ssh_session.read()
                    if data:
                        socketio.emit('terminal_data', {'data': data}, namespace='/', to=sid)
                except Exception as e:
                    print(f"Read output error: {e}")
                    break
                time.sleep(0.05)
        
        socketio.start_background_task(read_output, sid, ssh_session, socketio)
    else:
        emit('terminal_error', {'message': f'无法连接到节点 {node}'}, namespace='/')


@socketio.on('terminal_input')
def handle_terminal_input(data):
    """处理终端输入"""
    sid = request.sid
    print(f"收到终端输入: {data}, sid: {sid}")
    if sid in terminal_sessions:
        terminal_sessions[sid].write(data.get('data', ''))


@socketio.on('terminal_resize')
def handle_terminal_resize(data):
    """处理终端大小调整"""
    sid = request.sid
    if sid in terminal_sessions:
        terminal_sessions[sid].resize(
            data.get('width', 80),
            data.get('height', 24)
        )


@socketio.on('terminal_disconnect')
def handle_terminal_disconnect():
    """处理终端断开"""
    sid = request.sid
    if sid in terminal_sessions:
        terminal_sessions[sid].close()
        del terminal_sessions[sid]
        emit('terminal_disconnected', namespace='/')

# ============== Main ==============


# ============== Log API ==============

@app.route('/api/log')

@app.route('/api/log')
def api_log():
    """Get last 100 lines of a log file"""
    log_path = request.args.get('path', '')
    
    # Security check: only allow slurm log paths
    allowed_paths = [
        '/var/log/slurm/slurmctld.log',
        '/var/log/slurm/slurmd.log',
        '/var/log/slurm/slurmdbd.log'
    ]
    
    if log_path not in allowed_paths:
        return jsonify({'error': 'Invalid log path'}), 400
    
    try:
        # Get last 100 lines
        result = subprocess.run(
            ['tail', '-n', '100', log_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return jsonify({'content': result.stdout})
        else:
            return jsonify({'error': result.stderr}), 500
            
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Command timeout'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============== Statistics API ==============

def parse_sreport_user_top(days=7, top=10):
    """Get top users by CPU time"""
    output = run_command(f"timeout 3 sreport user topuser TopCount={top} -t hours --format=Login,Usage,Jobs,AcPU,Energy -T {days} 2>/dev/null || echo ''")
    users = []
    if output and not output.startswith("Error") and 'Slurm accounting storage is disabled' not in output:
        lines = output.split('\n')[2:]
        for line in lines:
            parts = line.split()
            if len(parts) >= 4:
                users.append({'login': parts[0], 'usage': parts[1], 'jobs': parts[2], 'cpu_time': parts[3], 'energy': parts[4] if len(parts) > 4 else 'N/A'})
    if not users:
        user_stats = get_user_stats()
        for user, stats in user_stats.items():
            users.append({'login': user, 'usage': '0', 'jobs': str(stats['jobs']), 'cpu_time': str(stats['cpus']), 'energy': 'N/A'})
    return users[:top]

def parse_sacct_stats(hours=24):
    """Get job statistics from sacct - Unified with get_user_resource_usage"""
    # Use unified function for consistent CPU time calculation
    resource_usage = get_user_resource_usage(hours)
    
    # Get basic job stats
    output = run_command(f"timeout 3 sacct -a -X --format=State,ExitCode,Partition,User -S now-{hours}hours --parsable2 --noheader 2>/dev/null || echo ''")
    stats = {'completed': 0, 'failed': 0, 'cancelled': 0, 'timeout': 0, 'total': 0, 
             'total_cpu_hours': round(resource_usage['total_cpu_minutes'] / 60, 2),
             'total_gpu_hours': round(resource_usage['total_gpu_minutes'] / 60, 2),
             'partitions': {}, 'users': {}}
    
    if output and not output.startswith("Error") and output.strip() and 'Slurm accounting storage is disabled' not in output:
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 4:
                state, exit_code, partition, user = parts[:4]
                stats['total'] += 1
                state_upper = state.upper()
                if state_upper in ['COMPLETED', 'CD']: stats['completed'] += 1
                elif state_upper in ['FAILED', 'F']: stats['failed'] += 1
                elif state_upper in ['CANCELLED', 'CA']: stats['cancelled'] += 1
                elif state_upper in ['TIMEOUT', 'TO']: stats['timeout'] += 1
                
                if partition not in stats['partitions']: 
                    stats['partitions'][partition] = {'jobs': 0, 'cpu_hours': 0}
                stats['partitions'][partition]['jobs'] += 1
                
                if user not in stats['users']: 
                    stats['users'][user] = {'jobs': 0, 'cpu_hours': 0}
                stats['users'][user]['jobs'] += 1
    else:
        # Fallback to squeue data
        jobs = parse_squeue()
        stats['total'] = len(jobs)
        for job in jobs:
            state = job['state']
            partition = job['partition']
            user = job['user']
            if state == 'R': stats['completed'] += 1
            elif state == 'PD': stats['cancelled'] += 1
            elif state in ['F', 'TO']: stats['failed'] += 1
            if partition not in stats['partitions']: 
                stats['partitions'][partition] = {'jobs': 0, 'cpu_hours': 0}
            stats['partitions'][partition]['jobs'] += 1
            if user not in stats['users']: 
                stats['users'][user] = {'jobs': 0, 'cpu_hours': 0}
            stats['users'][user]['jobs'] += 1
    
    # Add CPU hours per user from unified data
    for user_data in resource_usage['users']:
        user = user_data['user']
        cpu_hours = round(user_data['cpu_minutes'] / 60, 2)
        if user in stats['users']:
            stats['users'][user]['cpu_hours'] = cpu_hours
        else:
            stats['users'][user] = {'jobs': user_data['jobs'], 'cpu_hours': cpu_hours}
    
    return stats

def parse_node_utilization():
    """Get node utilization stats"""
    output = run_command("sinfo -N -o '%N|%C|%e|%O|%T' --noheader")
    nodes = []
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 5:
                nodes.append({'name': parts[0], 'cpus': parts[1], 'free_mem': parts[2], 'load': parts[3], 'state': parts[4]})
    return nodes

def parse_squeue_wait_times():
    """Get job wait times"""
    output = run_command("squeue -o '%i|%S|%b' -h -t PD 2>/dev/null")
    wait_times = []
    if output and not output.startswith("Error"):
        now = datetime.datetime.now()
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 2:
                job_id, submit_time = parts[:2]
                try:
                    submit = datetime.datetime.strptime(submit_time, '%Y-%m-%dT%H:%M:%S')
                    wait_times.append({'job_id': job_id, 'wait_minutes': (now - submit).total_seconds() / 60})
                except: pass
    return wait_times

@app.route('/api/stats/jobs')
def api_job_stats():
    hours = request.args.get('hours', 24, type=int)
    return jsonify(parse_sacct_stats(hours))

@app.route('/api/stats/users/top')
def api_user_top():
    """Get top users by CPU/GPU time - Unified with get_user_resource_usage"""
    days = request.args.get('days', 7, type=int)
    top = request.args.get('top', 10, type=int)
    
    # Use unified function for consistent statistics
    hours = days * 24
    result = get_user_resource_usage(hours)
    users = result['users']
    
    # Format for compatibility with existing code
    formatted_users = []
    for u in users[:top]:
        formatted_users.append({
            'login': u['user'],
            'usage': str(u['cpu_minutes']),
            'jobs': str(u['jobs']),
            'cpu_time': str(round(u['cpu_minutes'] / 60, 2)),  # Convert to hours
            'cpu_minutes': u['cpu_minutes'],
            'gpu_minutes': u['gpu_minutes'],
            'cpu_percent': u['cpu_percent'],
            'gpu_percent': u['gpu_percent'],
            'energy': 'N/A'
        })
    
    return jsonify(formatted_users)


@app.route('/api/stats/users/detailed')
def api_user_resource_usage_detailed():
    """Get detailed CPU/GPU resource usage for all users"""
    hours = request.args.get('hours', 168, type=int)  # Default 7 days
    result = get_user_resource_usage(hours)
    return jsonify(result)

@app.route('/api/stats/nodes')
def api_node_stats():
    return jsonify(parse_node_utilization())

@app.route('/api/stats/wait-times')
def api_wait_times():
    return jsonify(parse_squeue_wait_times())

@app.route('/api/history/jobs')
def api_job_history():
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', None, type=int)
    output = run_command(f"sacct -a -X --format=JobID,JobName,User,Partition,State,ExitCode,Start,End,Elapsed,CPUTime -S now-{hours}hours --parsable2 --noheader 2>/dev/null")
    jobs = []
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 10:
                jobs.append({'job_id': parts[0], 'name': parts[1], 'user': parts[2], 'partition': parts[3], 'state': parts[4], 'exit_code': parts[5], 'start': parts[6], 'end': parts[7], 'elapsed': parts[8], 'cpu_time': parts[9]})
    # Apply limit if specified
    if limit and limit > 0:
        jobs = jobs[:limit]
    return jsonify(jobs)


# ============== Enhanced Statistics API ==============

def parse_job_state_distribution(hours=24):
    """Get job state distribution for pie chart"""
    output = run_command(f"timeout 3 sacct -a -X --format=State -S now-{hours}hours --parsable2 --noheader 2>/dev/null || echo ''")
    distribution = {}
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            state = line.strip()
            if state:
                state_short = state.split()[0] if ' ' in state else state
                distribution[state_short] = distribution.get(state_short, 0) + 1
    return distribution

def parse_partition_usage(hours=24):
    """Get partition usage statistics"""
    output = run_command(f"timeout 3 sacct -a -X --format=Partition,State,Elapsed,CPUTime -S now-{hours}hours --parsable2 --noheader 2>/dev/null || echo ''")
    partitions = {}
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 4:
                partition, state, elapsed, cpu_time = parts[:4]
                if partition not in partitions:
                    partitions[partition] = {'jobs': 0, 'completed': 0, 'failed': 0, 'cpu_hours': 0}
                partitions[partition]['jobs'] += 1
                state_upper = state.upper()
                if state_upper in ['COMPLETED', 'CD']:
                    partitions[partition]['completed'] += 1
                elif state_upper in ['FAILED', 'F', 'TIMEOUT', 'TO', 'CANCELLED', 'CA']:
                    partitions[partition]['failed'] += 1
                # Parse CPU time
                try:
                    cpu_parts = cpu_time.split(':')
                    if len(cpu_parts) >= 3:
                        hours_val = int(cpu_parts[0].split('-')[-1])
                        minutes_val = int(cpu_parts[1])
                        partitions[partition]['cpu_hours'] += hours_val + minutes_val/60
                except:
                    pass
    return partitions

def parse_hourly_trend(hours=24):
    """Get hourly job submission trend"""
    output = run_command(f"timeout 3 sacct -a -X --format=Submit -S now-{hours}hours --parsable2 --noheader 2>/dev/null || echo ''")
    hourly = {}
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            submit_time = line.strip()
            if submit_time and 'T' in submit_time:
                try:
                    date = submit_time.split('T')[0]
                    hour = submit_time.split('T')[1].split(':')[0]
                    # 短时间范围(<=24h)只按小时聚合，长时间按日期+小时聚合
                    if hours <= 24:
                        key = hour
                    else:
                        # 简化为 MM-DD HH 格式
                        key = f"{date[5:]} {hour}"
                    hourly[key] = hourly.get(key, 0) + 1
                except:
                    pass
    
    # 对于24小时内的数据，填充缺失的小时
    if hours <= 24:
        for h in range(24):
            h_str = f"{h:02d}"
            if h_str not in hourly:
                hourly[h_str] = 0
    
    return dict(sorted(hourly.items()))

def parse_daily_trend(days=7):
    """Get daily job submission trend"""
    output = run_command(f"timeout 3 sacct -a -X --format=Submit -S now-{days}days --parsable2 --noheader 2>/dev/null || echo ''")
    daily = {}
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            submit_time = line.strip()
            if submit_time and 'T' in submit_time:
                try:
                    date = submit_time.split('T')[0]
                    daily[date] = daily.get(date, 0) + 1
                except:
                    pass
    return dict(sorted(daily.items()))

def parse_job_duration_distribution(hours=168):
    """Analyze job duration distribution"""
    output = run_command(f"timeout 3 sacct -a -X --format=Elapsed -S now-{hours}hours --parsable2 --noheader 2>/dev/null || echo ''")
    distribution = {'0-1h': 0, '1-6h': 0, '6-12h': 0, '12-24h': 0, '24h+': 0}
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            elapsed = line.strip()
            if elapsed:
                try:
                    # Parse duration like "01:30:00" or "1-12:30:00"
                    days = 0
                    if '-' in elapsed:
                        days, elapsed = elapsed.split('-')
                        days = int(days)
                    parts = elapsed.split(':')
                    if len(parts) >= 3:
                        hours = int(parts[0]) + days * 24
                        if hours < 1:
                            distribution['0-1h'] += 1
                        elif hours < 6:
                            distribution['1-6h'] += 1
                        elif hours < 12:
                            distribution['6-12h'] += 1
                        elif hours < 24:
                            distribution['12-24h'] += 1
                        else:
                            distribution['24h+'] += 1
                except:
                    pass
    return distribution

def parse_wait_time_analysis(hours=24):
    """Analyze job wait times"""
    output = run_command(f"timeout 3 sacct -a -X --format=Submit,Start -S now-{hours}hours --parsable2 --noheader 2>/dev/null || echo ''")
    wait_times = []
    if output and not output.startswith("Error"):
        now = datetime.datetime.now()
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 2:
                submit_str, start_str = parts[:2]
                if submit_str and start_str and 'T' in submit_str and 'T' in start_str:
                    try:
                        submit = datetime.datetime.strptime(submit_str, '%Y-%m-%dT%H:%M:%S')
                        start = datetime.datetime.strptime(start_str, '%Y-%m-%dT%H:%M:%S')
                        wait_minutes = (start - submit).total_seconds() / 60
                        if wait_minutes >= 0:
                            wait_times.append(wait_minutes)
                    except:
                        pass
    if wait_times:
        wait_times.sort()
        n = len(wait_times)
        return {
            'count': n,
            'avg_minutes': round(sum(wait_times) / n, 1),
            'median_minutes': round(wait_times[n // 2], 1),
            'min_minutes': round(wait_times[0], 1),
            'max_minutes': round(wait_times[-1], 1),
            'p95_minutes': round(wait_times[int(n * 0.95)], 1) if n >= 20 else None,
            'distribution': {
                '<5min': sum(1 for w in wait_times if w < 5),
                '5-30min': sum(1 for w in wait_times if 5 <= w < 30),
                '30min-2h': sum(1 for w in wait_times if 30 <= w < 120),
                '2-12h': sum(1 for w in wait_times if 120 <= w < 720),
                '12h+': sum(1 for w in wait_times if w >= 720)
            }
        }
    return {'count': 0}

def parse_node_efficiency(days=7):
    """Get node efficiency ranking"""
    output = run_command(f"timeout 3 sreport cluster utilization -t percent --format=Cluster,Allocated,Down,Idle,Reported -T {days} 2>/dev/null || echo ''")
    nodes = []
    if output and not output.startswith("Error"):
        lines = output.split('\n')[2:]
        for line in lines:
            parts = line.split()
            if len(parts) >= 5:
                try:
                    allocated = float(parts[1].rstrip('%'))
                    idle = float(parts[3].rstrip('%'))
                    down = float(parts[2].rstrip('%'))
                    efficiency = allocated / (allocated + idle + 0.1) * 100
                    nodes.append({
                        'name': parts[0],
                        'allocated': allocated,
                        'idle': idle,
                        'down': down,
                        'efficiency': round(efficiency, 1)
                    })
                except:
                    pass
    # Fallback to sinfo data
    if not nodes:
        node_info = parse_sinfo()
        for node in node_info:
            state = node['state'].lower()
            efficiency = 100 if 'alloc' in state else 50 if 'mix' in state else 0
            nodes.append({'name': node['name'], 'allocated': efficiency, 'idle': 100-efficiency, 'down': 0, 'efficiency': efficiency})
    return sorted(nodes, key=lambda x: x['efficiency'], reverse=True)

def parse_resource_efficiency(hours=24):
    """Calculate resource utilization efficiency"""
    output = run_command(f"timeout 3 sacct -a -X --format=ReqCPUS,CPUTime,Elapsed,State -S now-{hours}hours --parsable2 --noheader 2>/dev/null || echo ''")
    total_cpus = 0
    used_cpu_hours = 0
    completed_jobs = 0
    failed_jobs = 0
    
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 4:
                try:
                    req_cpus = int(parts[0]) if parts[0].isdigit() else 1
                    cpu_time = parts[1]
                    elapsed = parts[2]
                    state = parts[3].upper()
                    
                    # Parse CPU time to hours
                    cpu_hours = 0
                    if cpu_time and ':' in cpu_time:
                        cpu_parts = cpu_time.split(':')
                        if len(cpu_parts) >= 3:
                            cpu_hours = int(cpu_parts[0].split('-')[-1]) + int(cpu_parts[1])/60
                    
                    total_cpus += req_cpus
                    used_cpu_hours += cpu_hours
                    
                    if state in ['COMPLETED', 'CD']:
                        completed_jobs += 1
                    elif state in ['FAILED', 'F', 'TIMEOUT', 'TO']:
                        failed_jobs += 1
                except:
                    pass
    
    success_rate = round(completed_jobs / (completed_jobs + failed_jobs) * 100, 1) if (completed_jobs + failed_jobs) > 0 else 0
    
    return {
        'success_rate': success_rate,
        'completed_jobs': completed_jobs,
        'failed_jobs': failed_jobs,
        'total_jobs': completed_jobs + failed_jobs,
        'cpu_utilization': round(used_cpu_hours / max(total_cpus, 1) * 100, 1) if total_cpus > 0 else 0
    }

def parse_account_usage(days=7):
    """Get account usage statistics"""
    output = run_command(f"timeout 3 sreport account cluster AccountUtilizationByUser -t hours --format=Account,Login,Used -T {days} 2>/dev/null || echo ''")
    accounts = {}
    if output and not output.startswith("Error"):
        lines = output.split('\n')[2:]
        for line in lines:
            parts = line.split()
            if len(parts) >= 3:
                account, user, used = parts[0], parts[1], parts[2]
                if account not in accounts:
                    accounts[account] = {'users': {}, 'total_hours': 0}
                accounts[account]['users'][user] = used
                try:
                    accounts[account]['total_hours'] += float(used)
                except:
                    pass
    return accounts

# New API endpoints

@app.route('/api/stats/job-distribution')
def api_job_distribution():
    """Get job state distribution"""
    hours = request.args.get('hours', 24, type=int)
    return jsonify(parse_job_state_distribution(hours))

@app.route('/api/stats/partition-usage')
def api_partition_usage():
    """Get partition usage statistics"""
    hours = request.args.get('hours', 24, type=int)
    return jsonify(parse_partition_usage(hours))

@app.route('/api/stats/hourly-trend')
def api_hourly_trend():
    """Get hourly job submission trend"""
    hours = request.args.get('hours', 24, type=int)
    return jsonify(parse_hourly_trend(hours))

@app.route('/api/stats/daily-trend')
def api_daily_trend():
    """Get daily job submission trend"""
    days = request.args.get('days', 7, type=int)
    return jsonify(parse_daily_trend(days))

@app.route('/api/stats/duration-distribution')
def api_duration_distribution():
    """Get job duration distribution"""
    hours = request.args.get('hours', 168, type=int)
    return jsonify(parse_job_duration_distribution(hours))

@app.route('/api/stats/wait-time-analysis')
def api_wait_time_analysis():
    """Get wait time analysis"""
    hours = request.args.get('hours', 24, type=int)
    return jsonify(parse_wait_time_analysis(hours))

@app.route('/api/stats/node-efficiency')
def api_node_efficiency():
    """Get node efficiency ranking"""
    days = request.args.get('days', 7, type=int)
    return jsonify(parse_node_efficiency(days))

@app.route('/api/stats/resource-efficiency')
def api_resource_efficiency():
    """Get resource utilization efficiency"""
    hours = request.args.get('hours', 24, type=int)
    return jsonify(parse_resource_efficiency(hours))

@app.route('/api/stats/account-usage')
def api_account_usage():
    """Get account usage statistics"""
    days = request.args.get('days', 7, type=int)
    return jsonify(parse_account_usage(days))

@app.route('/api/stats/export')
def api_export_stats():
    """Export statistics as CSV"""
    hours = request.args.get('hours', 168, type=int)
    data_type = request.args.get('type', 'jobs')
    
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    if data_type == 'jobs':
        jobs = parse_sacct_history(hours)
        writer.writerow(['JobID', 'Name', 'User', 'Partition', 'State', 'ExitCode'])
        for job in jobs:
            writer.writerow([job['job_id'], job['name'], job['user'], job['partition'], job['state'], job['exit_code']])
    elif data_type == 'users':
        users = parse_sreport_user_top(days=hours//24, top=100)
        writer.writerow(['User', 'Usage', 'Jobs', 'CPU Time', 'Energy'])
        for user in users:
            writer.writerow([user['login'], user['usage'], user['jobs'], user['cpu_time'], user['energy']])
    
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={data_type}_stats.csv'})

@app.route('/test-chart')
def test_chart():
    return render_template('test_chart.html')





# ============== Resource Quota (Resource Binding) API ==============

@app.route('/api/resource-quotas')
def api_resource_quotas():
    """Get resource quotas for all associations (users/accounts)"""
    # Get associations with limits - 添加 MaxJobs 和 MaxSubmitJobs
    output = run_command(
        "sacctmgr show assoc format=Cluster,Account,User,Partition,QOS,GrpTRES,MaxTRES,MaxTRESPerUser,MaxWall,Fairshare,MaxJobs,MaxSubmitJobs --noheader --parsable2 2>/dev/null"
    )
    
    quotas = []
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 12:
                quotas.append({
                    'cluster': parts[0],
                    'account': parts[1],
                    'user': parts[2] if parts[2] else '(account)',
                    'partition': parts[3] if parts[3] else 'ALL',
                    'qos': parts[4] if parts[4] else '',
                    'grp_tres': parts[5] if parts[5] else 'N/A',
                    'max_tres': parts[6] if parts[6] else 'N/A',
                    'max_tres_per_user': parts[7] if parts[7] else 'N/A',
                    'max_wall': parts[8] if parts[8] else 'N/A',
                    'fairshare': parts[9] if parts[9] else 'parent',
                    'max_jobs': parts[10] if parts[10] else 'N/A',
                    'max_submit': parts[11] if parts[11] else 'N/A'
                })
    
    return jsonify(quotas)


@app.route('/api/resource-quotas/tres-types')
def api_tres_types():
    """Get available TRES types"""
    output = run_command("sacctmgr show tres --noheader --parsable2 2>/dev/null")
    
    tres_types = [
        {'type': 'cpu', 'name': 'CPU核心', 'example': '100'},
        {'type': 'mem', 'name': '内存', 'example': '500G'},
        {'type': 'gres/gpu', 'name': 'GPU', 'example': '10'},
        {'type': 'node', 'name': '节点', 'example': '5'},
    ]
    
    if output and not output.startswith("Error"):
        custom_tres = []
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 3:
                tres_type = parts[1]
                name = parts[2]
                if tres_type not in ['cpu', 'mem', 'node', 'billing', 'energy']:
                    custom_tres.append({'type': tres_type, 'name': name, 'example': '1'})
        tres_types.extend(custom_tres)
    
    return jsonify(tres_types)


@app.route('/api/resource-quotas/qos-limits')
def api_qos_limits():
    """Get QOS resource limits"""
    # 添加 MaxJobs 和 MaxSubmitJobs
    output = run_command(
        "sacctmgr show qos format=Name,GrpTRES,MaxTRES,MaxTRESPerUser,MaxWall,Priority,MaxJobs,MaxSubmitJobs --noheader --parsable2 2>/dev/null"
    )
    
    qos_limits = []
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 8:
                qos_limits.append({
                    'name': parts[0],
                    'grp_tres': parts[1] if parts[1] else 'N/A',
                    'max_tres': parts[2] if parts[2] else 'N/A',
                    'max_tres_per_user': parts[3] if parts[3] else 'N/A',
                    'max_wall': parts[4] if parts[4] else 'N/A',
                    'priority': parts[5] if parts[5] else '0',
                    'max_jobs': parts[6] if parts[6] else 'N/A',
                    'max_submit': parts[7] if parts[7] else 'N/A'
                })
    
    return jsonify(qos_limits)


@app.route('/api/resource-quotas/set', methods=['POST'])
def api_set_resource_quota():
    """Set resource quota for an association"""
    config = load_config()
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        data = request.json or {}
        password = data.get('password', '')
        if password != config.get('admin_password', 'admin888'):
            return jsonify({'success': False, 'message': '密码错误'}), 403
    
    data = request.json or {}
    entity_type = data.get('entity_type')  # 'user', 'account', 'qos'
    entity_name = data.get('entity_name')
    cluster = data.get('cluster', '')
    
    if not entity_type or not entity_name:
        return jsonify({'success': False, 'message': '实体类型和名称不能为空'}), 400
    
    # Build sacctmgr command
    set_parts = []
    
    if 'grp_tres' in data and data['grp_tres']:
        set_parts.append(f"GrpTRES={data['grp_tres']}")
    if 'max_tres' in data and data['max_tres']:
        set_parts.append(f"MaxTRES={data['max_tres']}")
    if 'max_tres_per_user' in data and data['max_tres_per_user']:
        set_parts.append(f"MaxTRESPerUser={data['max_tres_per_user']}")
    if 'max_wall' in data and data['max_wall']:
        set_parts.append(f"MaxWall={data['max_wall']}")
    if 'fairshare' in data and data['fairshare']:
        set_parts.append(f"Fairshare={data['fairshare']}")
    if 'max_jobs' in data and data['max_jobs']:
        set_parts.append(f"MaxJobs={data['max_jobs']}")
    if 'max_submit' in data and data['max_submit']:
        set_parts.append(f"MaxSubmit={data['max_submit']}")
    if 'priority' in data and data['priority']:
        set_parts.append(f"Priority={data['priority']}")
    
    if not set_parts:
        return jsonify({'success': False, 'message': '没有要设置的配额参数'}), 400
    
    # Build command based on entity type
    if entity_type == 'qos':
        command = f"sacctmgr -i modify qos where name={entity_name} set {' '.join(set_parts)}"
    elif entity_type == 'user':
        account = data.get('account', '')
        if account and cluster:
            command = f"sacctmgr -i modify user where name={entity_name} account={account} cluster={cluster} set {' '.join(set_parts)}"
        elif account:
            command = f"sacctmgr -i modify user where name={entity_name} account={account} set {' '.join(set_parts)}"
        else:
            command = f"sacctmgr -i modify user where name={entity_name} set {' '.join(set_parts)}"
    elif entity_type == 'account':
        if cluster:
            command = f"sacctmgr -i modify account where name={entity_name} cluster={cluster} set {' '.join(set_parts)}"
        else:
            command = f"sacctmgr -i modify account where name={entity_name} set {' '.join(set_parts)}"
    else:
        return jsonify({'success': False, 'message': '不支持的实体类型'}), 400
    
    result = run_command(command)
    
    if result and not result.startswith("Error"):
        return jsonify({'success': True, 'message': '资源配额设置成功'})
    else:
        return jsonify({'success': False, 'message': result or '命令执行失败'}), 500


@app.route('/api/resource-quotas/clear', methods=['POST'])
def api_clear_resource_quota():
    """Clear a specific resource quota (set to -1)"""
    config = load_config()
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        data = request.json or {}
        password = data.get('password', '')
        if password != config.get('admin_password', 'admin888'):
            return jsonify({'success': False, 'message': '密码错误'}), 403
    
    data = request.json or {}
    entity_type = data.get('entity_type')
    entity_name = data.get('entity_name')
    limit_name = data.get('limit_name')  # e.g., 'GrpTRES', 'MaxTRES', etc.
    
    if not all([entity_type, entity_name, limit_name]):
        return jsonify({'success': False, 'message': '参数不完整'}), 400
    
    if entity_type == 'qos':
        command = f"sacctmgr -i modify qos where name={entity_name} set {limit_name}=-1"
    elif entity_type == 'user':
        command = f"sacctmgr -i modify user where name={entity_name} set {limit_name}=-1"
    elif entity_type == 'account':
        command = f"sacctmgr -i modify account where name={entity_name} set {limit_name}=-1"
    else:
        return jsonify({'success': False, 'message': '不支持的实体类型'}), 400
    
    result = run_command(command)
    
    if result and not result.startswith("Error"):
        return jsonify({'success': True, 'message': '配额限制已清除'})
    else:
        return jsonify({'success': False, 'message': result or '命令执行失败'}), 500


# ============== QOS Management API ==============

@app.route('/api/qos')
def api_qos_list():
    """List all QOS configurations with resource limits"""
    # 获取基本QOS信息 + 资源配额字段
    output = run_command(
        "sacctmgr show qos format=Name,Priority,GraceTime,Preempt,PreemptMode,Flags,"
        "MaxSubmitJobsPerUser,MaxJobsPerUser,MaxWallDurationPerJob,MaxTRESPerJob,"
        "MaxTRESPerUser,MaxJobs,MaxSubmitJobs --noheader --parsable2 2>/dev/null"
    )
    
    qos_list = []
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 12:
                qos_list.append({
                    'name': parts[0],
                    'priority': parts[1] if parts[1] else '0',
                    'grace_time': parts[2] if parts[2] else '0',
                    'preempt': parts[3] if parts[3] else '',
                    'preempt_mode': parts[4] if parts[4] else '',
                    'flags': parts[5] if parts[5] else '',
                    # 资源配额字段
                    'max_submit_jobs_per_user': parts[6] if parts[6] else '',
                    'max_jobs_per_user': parts[7] if parts[7] else '',
                    'max_wall_duration_per_job': parts[8] if parts[8] else '',
                    'max_tres_per_job': parts[9] if parts[9] else '',
                    'max_tres_per_user': parts[10] if parts[10] else '',
                    'max_jobs': parts[11] if parts[11] else '',
                    'max_submit_jobs': parts[12] if len(parts) > 12 and parts[12] else ''
                })
    
    return jsonify(qos_list)


@app.route('/api/qos/<qos_name>')
def api_qos_detail(qos_name):
    """Get detailed QOS information"""
    # Get all QOS fields
    output = run_command(f"sacctmgr show qos where name={qos_name} --parsable2 2>/dev/null")
    
    if not output or output.startswith("Error"):
        return jsonify({'error': 'QOS not found'}), 404
    
    lines = output.strip().split('\n')
    if len(lines) < 2:
        return jsonify({'error': 'QOS not found'}), 404
    
    headers = lines[0].split('|')
    values = lines[1].split('|')
    
    qos_detail = {}
    for i, header in enumerate(headers):
        if i < len(values):
            qos_detail[header.lower()] = values[i]
    
    return jsonify(qos_detail)


@app.route('/api/qos', methods=['POST'])
def api_qos_create():
    """Create a new QOS"""
    config = load_config()
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        data = request.json or {}
        password = data.get('password', '')
        if password != config.get('admin_password', 'admin888'):
            return jsonify({'success': False, 'message': '密码错误'}), 403
    
    data = request.json or {}
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({'success': False, 'message': 'QOS名称不能为空'}), 400
    
    # Build sacctmgr command
    cmd_parts = [f"sacctmgr -i add qos {name}"]
    
    # Optional parameters
    if data.get('priority'):
        cmd_parts.append(f"Priority={data['priority']}")
    if data.get('description'):
        cmd_parts.append(f"Description='{data['description']}'")
    
    command = " ".join(cmd_parts)
    result = run_command(command)
    
    if result and not result.startswith("Error"):
        return jsonify({'success': True, 'message': f'QOS {name} 创建成功'})
    else:
        return jsonify({'success': False, 'message': result}), 500


@app.route('/api/qos/<qos_name>', methods=['PUT'])
def api_qos_modify(qos_name):
    """Modify a QOS"""
    config = load_config()
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        data = request.json or {}
        password = data.get('password', '')
        if password != config.get('admin_password', 'admin888'):
            return jsonify({'success': False, 'message': '密码错误'}), 403
    
    data = request.json or {}
    
    # Build modification command - only include non-empty values
    set_parts = []
    
    def add_param(key, param_name):
        """Add parameter if it exists and is not empty"""
        if key in data and data[key] and str(data[key]).strip():
            set_parts.append(f"{param_name}={data[key]}")
    
    add_param('priority', 'Priority')
    add_param('gracetime', 'GraceTime')
    add_param('flags', 'Flags')
    add_param('grptres', 'GrpTRES')
    add_param('maxtres', 'MaxTRES')
    add_param('maxwall', 'MaxWall')
    add_param('preempt', 'Preempt')
    add_param('usagefactor', 'UsageFactor')
    add_param('maxjobs', 'MaxJobs')
    add_param('maxsubmitjobs', 'MaxSubmitJobs')
    add_param('maxtresperjob', 'MaxTRESPerJob')
    add_param('maxtresperuser', 'MaxTRESPerUser')
    add_param('maxjobsperuser', 'MaxJobsPerUser')
    add_param('maxsubmitjobsperuser', 'MaxSubmitJobsPerUser')
    add_param('maxwalldurationperjob', 'MaxWallDurationPerJob')
    
    if not set_parts:
        return jsonify({'success': False, 'message': '没有要修改的参数'}), 400
    
    command = f"sacctmgr -i modify qos where name={qos_name} set {' '.join(set_parts)}"
    result = run_command(command)
    
    if result and not result.startswith("Error"):
        return jsonify({'success': True, 'message': f'QOS {qos_name} 修改成功'})
    else:
        return jsonify({'success': False, 'message': result}), 500


@app.route('/api/qos/<qos_name>', methods=['DELETE'])
def api_qos_delete(qos_name):
    """Delete a QOS"""
    config = load_config()
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        data = request.json or {}
        password = data.get('password', '')
        if password != config.get('admin_password', 'admin888'):
            return jsonify({'success': False, 'message': '密码错误'}), 403
    
    command = f"sacctmgr -i delete qos where name={qos_name}"
    result = run_command(command)
    
    if result and not result.startswith("Error"):
        return jsonify({'success': True, 'message': f'QOS {qos_name} 删除成功'})
    else:
        return jsonify({'success': False, 'message': result}), 500


@app.route('/api/qos/<qos_name>/associate', methods=['POST'])
def api_qos_associate(qos_name):
    """Associate QOS with account or user - add or remove qos"""
    config = load_config()
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        data = request.json or {}
        password = data.get('password', '')
        if password != config.get('admin_password', 'admin888'):
            return jsonify({'success': False, 'message': '密码错误'}), 403
    
    data = request.json or {}
    action = data.get('action', 'add')
    assoc_type = data.get('assoc_type', 'account')
    target = data.get('target', '')
    
    if not target:
        return jsonify({'success': False, 'message': '请输入账户或用户名称'}), 400
    
    if action == 'add':
        if assoc_type == 'account':
            command = f"sacctmgr -i modify account {target} set qos+={qos_name}"
        elif assoc_type == 'user':
            command = f"sacctmgr -i modify user {target} set qos+={qos_name}"
        else:
            return jsonify({'success': False, 'message': '无效的关联类型'}), 400
        op = '添加'
    elif action == 'remove':
        if assoc_type == 'account':
            command = f"sacctmgr -i modify account {target} set qos-={qos_name}"
        elif assoc_type == 'user':
            command = f"sacctmgr -i modify user {target} set qos-={qos_name}"
        else:
            return jsonify({'success': False, 'message': '无效的关联类型'}), 400
        op = '移除'
    else:
        return jsonify({'success': False, 'message': '无效的操作类型'}), 400
    
    result = run_command(command)
    
    if result and not result.startswith("Error"):
        return jsonify({'success': True, 'message': f'QOS {qos_name} {op}成功到 {assoc_type} {target}'})
    else:
        return jsonify({'success': False, 'message': result}), 500


@app.route('/api/qos/<qos_name>/associations')
def api_qos_associations(qos_name):
    """Get associations (users/accounts) using this QOS"""
    output = run_command(
        f"sacctmgr show assoc format=Cluster,Account,User,Partition,QOS --noheader --parsable2 2>/dev/null | grep '{qos_name}'"
    )
    
    associations = []
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 5:
                associations.append({
                    'cluster': parts[0],
                    'account': parts[1],
                    'user': parts[2],
                    'partition': parts[3],
                    'qos': parts[4]
                })
    
    return jsonify(associations)


# ============== Slurm Reservation API ==============

@app.route('/api/reservations')
def api_reservations():
    """Get all reservations"""
    reservations = parse_reservations()
    return jsonify(reservations)

@app.route('/api/reservations/<res_name>')
def api_reservation_detail(res_name):
    """Get reservation details by name"""
    output = run_command(f"scontrol show reservation {res_name}")
    details = {}
    if output and not output.startswith("Error"):
        for line in output.split('\n'):
            for match in re.finditer(r'(\w+)=(.+?)(?=\s+\w+=|$)', line):
                key, value = match.groups()
                details[key.lower()] = value.strip()
    return jsonify(details)

@app.route('/api/reservations', methods=['POST'])
def api_create_reservation():
    """Create a new reservation (requires admin)"""
    data = request.json
    required = ['reservationname', 'starttime', 'duration', 'nodes']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    cmd = f"scontrol create ReservationName={data['reservationname']} StartTime={data['starttime']} Duration={data['duration']} Nodes={data['nodes']}"
    
    if 'users' in data:
        cmd += f" Users={data['users']}"
    if 'accounts' in data:
        cmd += f" Accounts={data['accounts']}"
    if 'partitionname' in data:
        cmd += f" PartitionName={data['partitionname']}"
    if 'flags' in data:
        cmd += f" Flags={data['flags']}"
    
    result = run_command(cmd)
    if result.startswith("Error"):
        return jsonify({'error': result}), 500
    return jsonify({'message': 'Reservation created', 'result': result})

@app.route('/api/reservations/<res_name>', methods=['PUT'])
def api_update_reservation(res_name):
    """Update an existing reservation"""
    data = request.json
    cmd = f"scontrol update ReservationName={res_name}"
    
    for key, value in data.items():
        if key != 'reservationname':
            cmd += f" {key}={value}"
    
    result = run_command(cmd)
    if result.startswith("Error"):
        return jsonify({'error': result}), 500
    return jsonify({'message': 'Reservation updated', 'result': result})

@app.route('/api/reservations/<res_name>', methods=['DELETE'])
def api_delete_reservation(res_name):
    """Delete a reservation"""
    result = run_command(f"scontrol delete ReservationName={res_name}")
    if result.startswith("Error"):
        return jsonify({'error': result}), 500
    return jsonify({'message': 'Reservation deleted', 'result': result})


# ============== Slurm Account Management API ==============

@app.route('/api/accounts')
def api_accounts_list():
    """List all Slurm accounts with hierarchy"""
    # Get account basic info
    output = run_command("sacctmgr show account format=Account,Description,Organization --noheader --parsable2 2>/dev/null")
    
    accounts = {}
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 3:
                accounts[parts[0]] = {
                    'name': parts[0],
                    'description': parts[1] if parts[1] else '',
                    'organization': parts[2] if parts[2] else '',
                    'parent': ''
                }
    
    # Get parent info from assoc (more reliable)
    # Format: Account|ParentName|User - we need entries where User is empty (account associations)
    assoc_output = run_command("sacctmgr show assoc format=Account,ParentName,User --noheader --parsable2 2>/dev/null")
    if assoc_output and not assoc_output.startswith("Error"):
        for line in assoc_output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 3:
                account_name = parts[0]
                parent_name = parts[1]
                user_name = parts[2]
                # Only use account associations (User is empty) to get parent
                if account_name in accounts and not user_name and parent_name and parent_name != account_name:
                    accounts[account_name]['parent'] = parent_name
    
    return jsonify(list(accounts.values()))


@app.route('/api/accounts/tree')
def api_accounts_tree():
    """Get account hierarchy as a tree structure"""
    output = run_command("sacctmgr show account tree --noheader 2>/dev/null")
    
    tree = []
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            if line.strip():
                tree.append(line)
    
    return jsonify(tree)


@app.route('/api/organization-topology')
def api_organization_topology():
    """Get organization topology: QOS -> Account -> User hierarchy using tree format"""
    tree_output = run_command(
        "sacctmgr list associations tree format=Account,User,QOS,DefaultQOS 2>/dev/null"
    )
    
    topology = {
        'qos': [],
        'accounts': [],
        'users': [],
        'links': []
    }
    
    qos_quota_map = {}
    accounts_set = set()
    users_dict = {}
    used_qos = set()
    
    if tree_output and not tree_output.startswith("Error"):
        lines = tree_output.strip().split('\n')
        current_account = None
        current_qos = None
        account_qos_map = {}
        
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('Account') or stripped.startswith('-'):
                continue
            
            raw_account = line[0:20]
            user = line[20:40].strip()
            qos = line[40:60].strip()
            default_qos = line[60:70].strip()
            
            indent = len(line) - len(line.lstrip())
            account = raw_account.strip()
            
            if qos:
                for q in qos.split(','):
                    used_qos.add(q.strip())
            
            # indent=0: root根账户，完全忽略
            if indent == 0:
                continue
            
            # indent=1 + User为空: 统计account和qos的关系
            if indent == 1 and not user and account:
                current_account = account
                current_qos = qos
                account_qos_map[account] = qos
                if account not in accounts_set:
                    accounts_set.add(account)
                    topology['accounts'].append({
                        'name': account,
                        'quota': {
                            'default_qos': default_qos if default_qos else ''
                        }
                    })
                
                if qos:
                    for q in qos.split(','):
                        q_name = q.strip()
                        if q_name:
                            topology['links'].append({
                                'from': 'qos',
                                'from_name': q_name,
                                'to': 'account',
                                'to_name': account
                            })
            
            # indent=1 + User不为空: root用户，忽略
            # indent=2: 统计account->user->qos的关系
            elif indent >= 2 and user and current_account:
                if user not in users_dict:
                    users_dict[user] = {
                        'name': user,
                        'account': current_account,
                        'quota': {
                            'default_qos': default_qos if default_qos else ''
                        }
                    }
                    
                    topology['users'].append(users_dict[user])
                    
                    # 总是显示 account -> user 连线
                    topology['links'].append({
                        'from': 'account',
                        'from_name': current_account,
                        'to': 'user',
                        'to_name': user
                    })
                    
                    # 如果用户有独立的QOS（!=账户QOS），则QOS直接连线到用户
                    # 支持多个QOS（逗号分隔）
                    if qos and qos != current_qos:
                        qos_list = [q.strip() for q in qos.split(',') if q.strip()]
                        for user_qos in qos_list:
                            topology['links'].append({
                                'from': 'qos',
                                'from_name': user_qos,
                                'to': 'user',
                                'to_name': user
                            })
    
    if used_qos:
        qos_output = run_command(
            "sacctmgr show qos format=Name,GrpTRES,MaxTRES,MaxTRESPerUser,MaxWall,Priority,MaxJobs,MaxSubmitJobs,Preempt "
            "--noheader --parsable2 2>/dev/null"
        )
        
        if qos_output and not qos_output.startswith("Error"):
            for line in qos_output.strip().split('\n'):
                parts = line.split('|')
                if len(parts) >= 2 and parts[0] and parts[0] in used_qos:
                    qos_name = parts[0]
                    qos_quota_map[qos_name] = {
                        'name': qos_name,
                        'grp_tres': parts[1] if len(parts) > 1 and parts[1] else 'N/A',
                        'max_tres': parts[2] if len(parts) > 2 and parts[2] else 'N/A',
                        'max_wall': parts[4] if len(parts) > 4 and parts[4] else 'N/A',
                        'priority': parts[5] if len(parts) > 5 and parts[5] else 'N/A',
                        'max_jobs': parts[6] if len(parts) > 6 and parts[6] else 'N/A'
                    }
        
        for qos_name in used_qos:
            if qos_name in qos_quota_map:
                topology['qos'].append(qos_quota_map[qos_name])
                    
    return jsonify(topology)


@app.route('/api/accounts', methods=['POST'])
def api_account_create():
    """Create a new account"""
    config = load_config()
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        data = request.json or {}
        password = data.get('password', '')
        if password != config.get('admin_password', 'admin888'):
            return jsonify({'success': False, 'message': '密码错误'}), 403
    
    data = request.json or {}
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({'success': False, 'message': '账户名称不能为空'}), 400
    
    # Build command
    cmd_parts = [f"sacctmgr -i add account {name}"]
    
    if data.get('description'):
        cmd_parts.append(f"Description='{data['description']}'")
    if data.get('organization'):
        cmd_parts.append(f"Organization='{data['organization']}'")
    if data.get('parent'):
        cmd_parts.append(f"Parent={data['parent']}")
    if data.get('cluster'):
        cmd_parts.append(f"Cluster={data['cluster']}")
    
    command = " ".join(cmd_parts)
    result = run_command(command)
    
    if result and not result.startswith("Error"):
        return jsonify({'success': True, 'message': f'账户 {name} 创建成功'})
    else:
        return jsonify({'success': False, 'message': result}), 500


@app.route('/api/accounts/<account_name>', methods=['DELETE'])
def api_account_delete(account_name):
    """Delete an account"""
    config = load_config()
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        data = request.json or {}
        password = data.get('password', '')
        if password != config.get('admin_password', 'admin888'):
            return jsonify({'success': False, 'message': '密码错误'}), 403
    
    command = f"sacctmgr -i delete account where account={account_name}"
    result = run_command(command)
    
    if result and not result.startswith("Error"):
        return jsonify({'success': True, 'message': f'账户 {account_name} 删除成功'})
    else:
        return jsonify({'success': False, 'message': result}), 500


# ============== Slurm User Management API ==============

@app.route('/api/users')
def api_users_list():
    """List all Slurm users with their associations"""
    output = run_command("sacctmgr show user format=User,DefaultAccount,DefaultWCKey,AdminLevel --noheader --parsable2 2>/dev/null")
    
    users = []
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 4:
                users.append({
                    'name': parts[0],
                    'default_account': parts[1] if parts[1] else '',
                    'default_wckey': parts[2] if parts[2] else '',
                    'admin_level': parts[3] if parts[3] else 'None'
                })
    
    return jsonify(users)


@app.route('/api/users/<username>/associations')
def api_user_associations(username):
    """Get user's associations"""
    output = run_command(
        f"sacctmgr show assoc where user={username} format=Cluster,Account,Partition,QOS,DefaultQOS --noheader --parsable2 2>/dev/null"
    )
    
    associations = []
    if output and not output.startswith("Error"):
        for line in output.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 5:
                associations.append({
                    'cluster': parts[0],
                    'account': parts[1],
                    'partition': parts[2] if parts[2] else 'ALL',
                    'qos': parts[3] if parts[3] else '',
                    'default_qos': parts[4] if parts[4] else ''
                })
    
    return jsonify(associations)


@app.route('/api/users', methods=['POST'])
def api_user_create():
    """Create a new user association"""
    config = load_config()
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        data = request.json or {}
        password = data.get('password', '')
        if password != config.get('admin_password', 'admin888'):
            return jsonify({'success': False, 'message': '密码错误'}), 403
    
    data = request.json or {}
    name = data.get('name', '').strip()
    account = data.get('account', '').strip()
    
    if not name or not account:
        return jsonify({'success': False, 'message': '用户名和默认账户不能为空'}), 400
    
    # Build command
    cmd_parts = [f"sacctmgr -i add user {name} Account={account}"]
    
    if data.get('cluster'):
        cmd_parts.append(f"Cluster={data['cluster']}")
    if data.get('partition'):
        cmd_parts.append(f"Partition={data['partition']}")
    if data.get('qos'):
        cmd_parts.append(f"QOS={data['qos']}")
    if data.get('admin_level'):
        cmd_parts.append(f"AdminLevel={data['admin_level']}")
    
    command = " ".join(cmd_parts)
    result = run_command(command)
    
    if result and not result.startswith("Error"):
        return jsonify({'success': True, 'message': f'用户 {name} 创建成功'})
    else:
        return jsonify({'success': False, 'message': result}), 500


@app.route('/api/users/<username>', methods=['PUT'])
def api_user_modify(username):
    """Modify a user"""
    config = load_config()
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        data = request.json or {}
        password = data.get('password', '')
        if password != config.get('admin_password', 'admin888'):
            return jsonify({'success': False, 'message': '密码错误'}), 403
    
    data = request.json or {}
    
    set_parts = []
    if 'default_account' in data:
        set_parts.append(f"DefaultAccount={data['default_account']}")
    if 'admin_level' in data:
        set_parts.append(f"AdminLevel={data['admin_level']}")
    if 'qos' in data:
        set_parts.append(f"QOS={data['qos']}")
    
    if not set_parts:
        return jsonify({'success': False, 'message': '没有要修改的参数'}), 400
    
    command = f"sacctmgr -i modify user where name={username} set {' '.join(set_parts)}"
    result = run_command(command)
    
    if result and not result.startswith("Error"):
        return jsonify({'success': True, 'message': f'用户 {username} 修改成功'})
    else:
        return jsonify({'success': False, 'message': result}), 500


@app.route('/api/associations', methods=['POST'])
def api_association_create():
    """Create a new association (user-account link)"""
    config = load_config()
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        data = request.json or {}
        password = data.get('password', '')
        if password != config.get('admin_password', 'admin888'):
            return jsonify({'success': False, 'message': '密码错误'}), 403
    
    data = request.json or {}
    user = data.get('user', '').strip()
    account = data.get('account', '').strip()
    
    if not user or not account:
        return jsonify({'success': False, 'message': '用户和账户不能为空'}), 400
    
    # Build command
    cmd_parts = [f"sacctmgr -i add user {user} Account={account}"]
    
    if data.get('cluster'):
        cmd_parts.append(f"Cluster={data['cluster']}")
    if data.get('partition'):
        cmd_parts.append(f"Partition={data['partition']}")
    if data.get('qos'):
        cmd_parts.append(f"QOS={data['qos']}")
    
    command = " ".join(cmd_parts)
    result = run_command(command)
    
    if result and not result.startswith("Error"):
        return jsonify({'success': True, 'message': f'关联创建成功'})
    else:
        return jsonify({'success': False, 'message': result}), 500


@app.route('/api/associations', methods=['DELETE'])
def api_association_delete():
    """Delete an association"""
    config = load_config()
    is_admin_session = session.get('user_type') == 'admin'
    if config.get('password_enabled', True) and not is_admin_session:
        data = request.json or {}
        password = data.get('password', '')
        if password != config.get('admin_password', 'admin888'):
            return jsonify({'success': False, 'message': '密码错误'}), 403
    
    data = request.json or {}
    user = data.get('user', '').strip()
    account = data.get('account', '').strip()
    
    if not user or not account:
        return jsonify({'success': False, 'message': '用户和账户不能为空'}), 400
    
    command = f"sacctmgr -i delete assoc where user={user} and account={account}"
    result = run_command(command)
    
    if result and not result.startswith("Error"):
        return jsonify({'success': True, 'message': f'关联删除成功'})
    else:
        return jsonify({'success': False, 'message': result}), 500


# ============== Job Submission API ==============

def verify_user_password(username, password):
    """Verify user password using PAM or su command"""
    try:
        # Method 1: Try using python-pam if available
        try:
            import pam
            p = pam.pam()
            if p.authenticate(username, password):
                return True
        except ImportError:
            pass
        
        # Method 2: Use su command to verify password
        # This is a workaround if python-pam is not available
        import subprocess
        proc = subprocess.Popen(
            ['su', '-', username, '-c', 'echo OK'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate(input=password + '\n', timeout=5)
        return 'OK' in stdout or proc.returncode == 0
    except Exception as e:
        print(f"Password verification error: {e}")
        return False


@app.route('/api/jobs/submit', methods=['POST'])
def api_submit_job():
    """Submit a new job to Slurm"""
    # Check if user is logged in
    if 'user_type' not in session:
        return jsonify({'success': False, 'message': '请先登录'}), 401
    
    # Get current logged in username
    username = session.get('username')
    
    # Handle both JSON and multipart form data
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form.to_dict()
        uploaded_files = request.files.getlist('files')
    else:
        data = request.json or {}
        uploaded_files = []
    
    # Get user credentials - now use session username
    if not username:
        return jsonify({'success': False, 'message': '无法获取用户信息'}), 400
    
    # Build sbatch command options
    options = []
    
    if data.get('name'):
        options.append(f"--job-name={data['name']}")
    if data.get('partition'):
        options.append(f"--partition={data['partition']}")
    if data.get('cpus'):
        options.append(f"--cpus-per-task={data['cpus']}")
    if data.get('memory'):
        options.append(f"--mem={data['memory']}G")
    if data.get('gpus') and int(data['gpus']) > 0:
        options.append(f"--gres=gpu:{data['gpus']}")
    if data.get('nodes'):
        options.append(f"--nodes={data['nodes']}")
    if data.get('time'):
        options.append(f"--time={data['time']}")
    if data.get('account'):
        options.append(f"--account={data['account']}")
    
    # Handle output directory
    output_dir = data.get('output_dir', '').strip()
    
    # Handle QOS - only add if explicitly specified
    qos = data.get('qos', '').strip()
    if qos and qos.lower() not in ('', 'none', 'null'):
        import re
        if re.match(r'^[\w-]+$', qos):
            options.append(f"--qos={qos}")
        else:
            return jsonify({'success': False, 'message': f'无效的QOS名称: {qos}'}), 400
    
    # Create a temporary script file in user's home directory
    import tempfile
    import os
    
    command = data.get('command', '#!/bin/bash\necho "Hello World"')
    if not command.startswith('#!'):
        command = '#!/bin/bash\n' + command
    
    try:
        # Get user's home directory
        import pwd
        try:
            user_info = pwd.getpwnam(username)
            user_home = user_info.pw_dir
            user_uid = user_info.pw_uid
            user_gid = user_info.pw_gid
        except KeyError:
            return jsonify({'success': False, 'message': f'用户 {username} 不存在'}), 400
        
        # Determine working directory
        work_dir = output_dir if output_dir else user_home
        # Expand ~ to home directory
        if work_dir.startswith('~'):
            work_dir = work_dir.replace('~', user_home, 1)
        work_dir = os.path.expanduser(work_dir)
        
        # Verify output directory exists and is writable by user
        if not os.path.exists(work_dir):
            return jsonify({'success': False, 'message': f'输出目录不存在: {work_dir}'}), 400
        
        # Check directory ownership/permissions
        try:
            dir_stat = os.stat(work_dir)
            # Directory should be owned by user or writable
            if dir_stat.st_uid != user_uid and not (dir_stat.st_mode & 0o002):
                return jsonify({'success': False, 'message': f'输出目录没有写权限: {work_dir}'}), 403
        except OSError as e:
            return jsonify({'success': False, 'message': f'无法访问输出目录: {e}'}), 400
        
        # Handle file uploads
        uploaded_file_paths = []
        if uploaded_files:
            for file in uploaded_files:
                if file and file.filename:
                    # Secure filename
                    from werkzeug.utils import secure_filename
                    filename = secure_filename(file.filename)
                    if not filename:
                        continue
                    
                    # Save to working directory
                    file_path = os.path.join(work_dir, filename)
                    file.save(file_path)
                    os.chown(file_path, user_uid, user_gid)
                    uploaded_file_paths.append(file_path)
        
        # Create job script in working directory
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False, dir=work_dir) as f:
            f.write(command)
            script_path = f.name
        
        # Change ownership to user
        os.chown(script_path, user_uid, user_gid)
        os.chmod(script_path, 0o755)
        
        # Set output/error file paths if output directory specified
        if output_dir:
            job_name = data.get('name', 'job')
            output_pattern = os.path.join(work_dir, f"{job_name}-%j.out")
            options.append(f"--output={output_pattern}")
            options.append(f"--error={output_pattern}")
        
        # Submit job as the user using su with full login environment
        cmd_options = ' '.join(options)
        submit_cmd = f"su - {username} -c 'cd {work_dir} && source /etc/profile && sbatch {cmd_options} {script_path}'"
        result = run_command(submit_cmd)
        
        # Clean up temp file
        try:
            os.unlink(script_path)
        except:
            pass
        
        if result and not result.startswith("Error"):
            import re
            match = re.search(r'Submitted batch job (\d+)', result)
            if match:
                job_id = match.group(1)
                return jsonify({'success': True, 'job_id': job_id, 'message': result, 'work_dir': work_dir, 'uploaded_files': uploaded_file_paths})
            else:
                return jsonify({'success': True, 'message': result, 'work_dir': work_dir, 'uploaded_files': uploaded_file_paths})
        else:
            return jsonify({'success': False, 'message': result}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ============== Main ==============

if __name__ == '__main__':
    print("=" * 50)
    print("  Slurm 集群监控系统 v1.3.0")
    print("  支持 Socket.IO 实时更新")
    print("=" * 50)
    print("")
    print("正在启动服务...")
    print("请在浏览器中访问: http://localhost:5000")
    print("")
    print("按 Ctrl+C 停止服务")
    print("=" * 50)
    print("")
    
    gpu_updater = GPUCacheUpdater(interval=10)
    gpu_updater.daemon = True
    gpu_updater.start()
    
    # Run SocketIO server
    socketio.run(app, host='0.0.0.0', port=5100, debug=False, allow_unsafe_werkzeug=True)


# ============== Job Submission API ==============

def verify_user_password(username, password):
    """Verify user password using PAM or su command"""
    try:
        # Method 1: Try using python-pam if available
        try:
            import pam
            p = pam.pam()
            if p.authenticate(username, password):
                return True
        except ImportError:
            pass
        
        # Method 2: Use su command to verify password
        # This is a workaround if python-pam is not available
        import subprocess
        proc = subprocess.Popen(
            ['su', '-', username, '-c', 'echo OK'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate(input=password + '\n', timeout=5)
        return 'OK' in stdout or proc.returncode == 0
    except Exception as e:
        print(f"Password verification error: {e}")
        return False


# ============== Main ==============

if __name__ == '__main__':
    print("=" * 50)
    print("  Slurm 集群监控系统 v1.3.0")
    print("  支持 Socket.IO 实时更新")
    print("=" * 50)
    print("")
    print("正在启动服务...")
    print("请在浏览器中访问: http://localhost:5000")
    print("")
    print("按 Ctrl+C 停止服务")
    print("=" * 50)
    print("")
    
    # Note: Background updater disabled - using frontend polling instead
    # updater.start()
    
    # Run SocketIO server
    socketio.run(app, host='0.0.0.0', port=5100, debug=False, allow_unsafe_werkzeug=True)
