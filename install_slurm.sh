#!/bin/bash

set -e

SLURM_VERSION="25.11.3"
SLURM_SOURCE="/root/slurm-install/slurm-25.11.3.tar.bz2"
INSTALL_PREFIX="/usr/local"
SLURM_USER="slurm"
SLURM_GROUP="slurm"

CLUSTER_NAME="cluster1"
SLURMCTLD_HOST=$(hostname)
SLURM_HOST_ADDR=$(hostname -I | awk '{print $1}')

CPU_COUNT=$(nproc)
REAL_MEMORY=$(free -m | awk '/Mem:/ {print $2}')
SOCKET_COUNT=$(lscpu | grep "Socket(s):" | awk '{print $2}')
CORE_PER_SOCKET=$(lscpu | grep "Core(s) per socket:" | awk '{print $4}')
THREAD_PER_CORE=$(lscpu | grep "Thread(s) per core:" | awk '{print $4}')

GPU_COUNT=0
GPU_TYPE=""
if command -v nvidia-smi &> /dev/null; then
    GPU_COUNT=$(nvidia-smi --query-gpu=gpu_name --format=csv,noheader | wc -l)
    GPU_TYPE=$(nvidia-smi --query-gpu=gpu_name --format=csv,noheader | head -1 | tr ' ' '_' | tr '[:upper:]' '[:lower:]')
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

install_dependencies() {
    log_info "Installing dependencies..."

    apt-get update

    DEPS="wget git gcc make libssl-dev libpam0g-dev libnuma-dev libhwloc-dev \
          librrd-dev libjson-c-dev libdbus-1-dev libsystemd-dev \
          libmariadb-dev libjwt-dev libhttp-parser-dev liblua5.3-dev \
          munge libmunge-dev"

    for pkg in $DEPS; do
        if ! dpkg -l | grep -q "^ii  $pkg "; then
            apt-get install -y $pkg
        fi
    done

    log_info "Dependencies installed"
}

extract_source() {
    log_info "Extracting SLURM source..."

    if [[ -d "/root/slurm-${SLURM_VERSION}" ]]; then
        log_warn "Source directory already exists, skipping extraction"
    else
        tar -xjf "$SLURM_SOURCE" -C /root/
    fi

    log_info "Source extracted to /root/slurm-${SLURM_VERSION}"
}

configure_slurm() {
    log_info "Configuring SLURM with REST API support..."

    cd /root/slurm-${SLURM_VERSION}

    ./configure \
        --prefix=${INSTALL_PREFIX} \
        --enable-slurmrestd \
        --with-slurmrestd-port=6820 \
        --enable-pam \
        --enable-multiple-slurmd \
        --enable-cgroupv2 \
        --with-munge \
        --sysconfdir=/etc/slurm \
        --localstatedir=/var \
        --enable-shared \
        --enable-static

    log_info "Configuration complete"
}

compile_slurm() {
    log_info "Compiling SLURM (this may take a while)..."

    cd /root/slurm-${SLURM_VERSION}
    make -j$(nproc)

    log_info "Compilation complete"
}

install_slurm() {
    log_info "Installing SLURM..."

    cd /root/slurm-${SLURM_VERSION}
    make install

    ldconfig

    log_info "SLURM installed to ${INSTALL_PREFIX}"
}

create_user_and_directories() {
    log_info "Creating SLURM user and directories..."

    if ! id "$SLURM_USER" &>/dev/null; then
        useradd -r -s /bin/false "$SLURM_USER"
        log_info "User $SLURM_USER created"
    else
        log_warn "User $SLURM_USER already exists"
    fi

    mkdir -p /etc/slurm
    mkdir -p /var/spool/slurm/ctld
    mkdir -p /var/spool/slurm/d
    mkdir -p /var/log/slurm

    chown -R ${SLURM_USER}:${SLURM_GROUP} /var/spool/slurm /var/log/slurm
    chmod 755 /var/spool/slurm /var/log/slurm

    log_info "User and directories created"
}

install_systemd_services() {
    log_info "Installing systemd service files..."

    cp /root/slurm-${SLURM_VERSION}/etc/slurmctld.service /lib/systemd/system/
    cp /root/slurm-${SLURM_VERSION}/etc/slurmd.service /lib/systemd/system/
    cp /root/slurm-${SLURM_VERSION}/etc/slurmdbd.service /lib/systemd/system/
    cp /root/slurm-${SLURM_VERSION}/etc/slurmrestd.service /lib/systemd/system/

    systemctl daemon-reload

    log_info "Systemd services installed"
}

configure_slurm_files() {
    log_info "Creating SLURM configuration files..."

    cat > /etc/slurm/slurm.conf << EOF
# Slurm Configuration File for Version ${SLURM_VERSION}
ClusterName=${CLUSTER_NAME}
SlurmctldHost=${SLURMCTLD_HOST}
SlurmUser=${SLURM_USER}
SlurmdUser=root

# Logging
SlurmctldLogFile=/var/log/slurm/slurmctld.log
SlurmdLogFile=/var/log/slurm/slurmd.log
SlurmdSpoolDir=/var/spool/slurm/d
StateSaveLocation=/var/spool/slurm/ctld

# Authentication
AuthType=auth/munge
CredType=cred/munge

# GRES (Generic Resource) - GPU Support
GresTypes=gpu

# Scheduling
SchedulerType=sched/backfill
SelectType=select/cons_tres
SelectTypeParameters=CR_Core_Memory
PriorityType=priority/basic

# Resource Allocation
ReturnToService=2

# Timeouts
SlurmctldTimeout=300
SlurmdTimeout=300
MinJobAge=300
KillWait=30
Waittime=0

# Node Configuration
NodeName=${SLURMCTLD_HOST} CPUs=${CPU_COUNT} Boards=1 SocketsPerBoard=${SOCKET_COUNT} \
    CoresPerSocket=${CORE_PER_SOCKET} ThreadsPerCore=${THREAD_PER_CORE} RealMemory=${REAL_MEMORY} \
EOF

    if [[ $GPU_COUNT -gt 0 && -n "$GPU_TYPE" ]]; then
        echo "    Gres=gpu:${GPU_TYPE}:${GPU_COUNT} State=UNKNOWN" >> /etc/slurm/slurm.conf
    else
        echo "    State=UNKNOWN" >> /etc/slurm/slurm.conf
    fi

    cat >> /etc/slurm/slurm.conf << EOF

# Partition Configuration
PartitionName=compute Nodes=${SLURMCTLD_HOST} Default=YES MaxTime=INFINITE State=UP
PartitionName=debug Nodes=${SLURMCTLD_HOST} Default=NO MaxTime=00:30:00 State=UP PriorityTier=100
EOF

    if [[ $GPU_COUNT -gt 0 ]]; then
        cat >> /etc/slurm/slurm.conf << EOF
PartitionName=gpu Nodes=${SLURMCTLD_HOST} Default=NO MaxTime=INFINITE State=UP
EOF
    fi

    cat >> /etc/slurm/slurm.conf << EOF

# Task Plugin
TaskPlugin=task/affinity,task/cgroup

# Proctrack
ProctrackType=proctrack/cgroup

# Communication
SlurmctldPort=6817
SlurmdPort=6818

# Debug Level
SlurmctldDebug=3
SlurmdDebug=3

# Other Settings
MpiDefault=pmi2
KillOnBadExit=1
EOF

    if [[ $GPU_COUNT -gt 0 && -n "$GPU_TYPE" ]]; then
        cat > /etc/slurm/gres.conf << EOF
# Slurm GRES (Generic Resource) Configuration File
NodeName=${SLURMCTLD_HOST} Name=gpu Type=${GPU_TYPE} File=/dev/nvidia0
EOF
    else
        touch /etc/slurm/gres.conf
    fi

    cat > /etc/slurm/cgroup.conf << EOF
# Slurm cgroup Configuration File
CgroupMountpoint=/sys/fs/cgroup

ConstrainCores=yes
ConstrainRAMSpace=yes
ConstrainSwapSpace=yes
ConstrainDevices=yes

AllowedDevicesFile=/etc/slurm/cgroup_allowed_devices_file.conf

AllowedRAMSpace=100
AllowedSwapSpace=0
MaxRAMPercent=100
MaxSwapPercent=0
MinRAMSpace=30
EOF

    cat > /etc/slurm/cgroup_allowed_devices_file.conf << EOF
/dev/null
/dev/zero
/dev/random
/dev/urandom
/dev/stdin
/dev/stdout
/dev/stderr
/dev/tty
/dev/full
/dev/ptmx
/dev/pts/*
EOF

    if [[ $GPU_COUNT -gt 0 ]]; then
        cat >> /etc/slurm/cgroup_allowed_devices_file.conf << EOF
/dev/nvidia*
/dev/nvidiactl
/dev/nvidia-modeset
/dev/nvidia-uvm
/dev/nvidia-uvm-tools
/dev/nvidia-caps/*
EOF
    fi

    chmod 644 /etc/slurm/slurm.conf
    chmod 644 /etc/slurm/cgroup.conf
    chmod 644 /etc/slurm/gres.conf
    chmod 644 /etc/slurm/cgroup_allowed_devices_file.conf
    chown -R ${SLURM_USER}:${SLURM_GROUP} /etc/slurm

    touch /var/log/slurm/slurmctld.log
    touch /var/log/slurm/slurmd.log
    chown ${SLURM_USER}:${SLURM_GROUP} /var/log/slurm/*.log

    log_info "Configuration files created"
}

setup_munge() {
    log_info "Setting up munge authentication..."

    if [[ ! -f /etc/munge/munge.key ]]; then
        create-munge-key -f
        chown munge:munge /etc/munge/munge.key
        chmod 400 /etc/munge/munge.key
    fi

    systemctl enable munge
    systemctl start munge

    log_info "Munge authentication configured"
}

start_slurm_services() {
    log_info "Starting SLURM services..."

    systemctl unmask slurmctld 2>/dev/null || true
    systemctl unmask slurmd 2>/dev/null || true
    systemctl unmask slurmrestd 2>/dev/null || true

    systemctl enable slurmctld
    systemctl enable slurmd
    systemctl enable slurmrestd

    systemctl start slurmctld
    sleep 2
    systemctl start slurmd
    sleep 2
    systemctl start slurmrestd

    log_info "SLURM services started"
}

verify_installation() {
    log_info "Verifying installation..."

    echo ""
    echo "=== SLURM Installation Summary ==="
    echo "Version: ${SLURM_VERSION}"
    echo "Install Prefix: ${INSTALL_PREFIX}"
    echo "Cluster Name: ${CLUSTER_NAME}"
    echo "Control Host: ${SLURMCTLD_HOST}"
    echo "CPU Count: ${CPU_COUNT}"
    echo "Memory: ${REAL_MEMORY} MB"
    echo "GPU Count: ${GPU_COUNT}"
    if [[ -n "$GPU_TYPE" ]]; then
        echo "GPU Type: ${GPU_TYPE}"
    fi
    echo ""

    echo "=== Service Status ==="
    systemctl is-active munge && echo "munge: running" || echo "munge: NOT running"
    systemctl is-active slurmctld && echo "slurmctld: running" || echo "slurmctld: NOT running"
    systemctl is-active slurmd && echo "slurmd: running" || echo "slurmd: NOT running"
    systemctl is-active slurmrestd && echo "slurmrestd: running" || echo "slurmrestd: NOT running"
    echo ""

    echo "=== Cluster Status ==="
    sinfo 2>/dev/null || log_warn "sinfo command failed"
    echo ""

    echo "=== REST API ==="
    echo "REST API is enabled on port 6820"
    echo "Test with: curl http://localhost:6820/slurm/v0.0.40/diag"
    echo ""

    log_info "Installation complete!"
}

main() {
    log_info "Starting SLURM ${SLURM_VERSION} automated installation with REST API support..."
    log_info "Hostname: ${SLURMCTLD_HOST}, IP: ${SLURM_HOST_ADDR}"
    if [[ $GPU_COUNT -gt 0 ]]; then
        log_info "GPU detected: ${GPU_COUNT}x ${GPU_TYPE}"
    fi

    check_root
    install_dependencies
    extract_source
    configure_slurm
    compile_slurm
    install_slurm
    create_user_and_directories
    install_systemd_services
    setup_munge
    configure_slurm_files
    start_slurm_services
    verify_installation
}

main "$@"
