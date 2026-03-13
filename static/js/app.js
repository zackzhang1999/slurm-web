/**
 * Slurm Monitor - Frontend Application
 * Version: 1.2.0 - Simplified (no external CDN)
 */

// Global state
let autoRefresh = true;
let refreshInterval = null;
let currentData = {};
let pendingCancelJobId = null;  // Store job ID waiting for password verification
let pendingCancelJobs = [];     // Store batch job IDs waiting for password verification
let historyDataAll = [];        // Store all history data for filtering
let historyShowAll = false;     // Flag to show all history records

// State color mapping
const STATE_COLORS = {
    'R': '#2ecc71', 'PD': '#f39c12', 'S': '#9b59b6', 'ST': '#9b59b6', 'CG': '#3498db',
    'idle': '#2ecc71', 'alloc': '#f39c12', 'mix': '#9b59b6', 'down': '#e74c3c', 'drain': '#e67e22', 'fail': '#e74c3c'
};

const STATE_LABELS = {
    'R': '运行中', 'PD': '等待中', 'S': '暂停', 'ST': '停止', 'CG': '完成中',
    'idle': '空闲', 'alloc': '已分配', 'mix': '混合', 'down': '故障', 'drain': '排空', 'fail': '失败'
};

// Initialize application
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded');
    initializeApp();
});

function initializeApp() {
    setupNavigation();
    setupEventListeners();
    loadAllData();
    toggleAutoRefresh(true);
}

// ==================== Navigation ====================
function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const pages = document.querySelectorAll('.page');
    
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const targetPage = item.dataset.page;
            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');
            pages.forEach(p => p.classList.remove('active'));
            document.getElementById(`page-${targetPage}`).classList.add('active');
            document.getElementById('page-title').textContent = item.querySelector('span:last-child').textContent;
            
            // Load page-specific data
            if (targetPage === 'statistics') {
                loadStatistics();
            } else if (targetPage === 'config') {
                loadConfig();
            } else if (targetPage === 'logs') {
                loadLog('slurmctld');
                loadLog('slurmd');
            }
        });
    });
}

// ==================== Event Listeners ====================
function setupEventListeners() {
    document.getElementById('refresh-btn').addEventListener('click', () => loadAllData());
    
    document.getElementById('auto-refresh-btn').addEventListener('click', (e) => {
        autoRefresh = !autoRefresh;
        toggleAutoRefresh(autoRefresh);
        e.currentTarget.innerHTML = autoRefresh ? '<span>▶️</span> 自动刷新' : '<span>⏸️</span> 已暂停';
    });
    
    document.getElementById('global-search').addEventListener('input', (e) => {
        const term = e.target.value.toLowerCase();
        filterTables(term);
    });
    
    document.querySelectorAll('.close-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.modal').forEach(m => m.classList.remove('active'));
        });
    });
    
    // Stats page refresh button
    const refreshStatsBtn = document.getElementById('refresh-stats-btn');
    if (refreshStatsBtn) {
        refreshStatsBtn.addEventListener('click', () => loadStatistics());
    }
    
    // Stats time range change
    const statsTimeRange = document.getElementById('stats-time-range');
    if (statsTimeRange) {
        statsTimeRange.addEventListener('change', () => loadStatistics());
    }
    
    // Show all history button
    const showAllHistoryBtn = document.getElementById('show-all-history-btn');
    if (showAllHistoryBtn) {
        showAllHistoryBtn.addEventListener('click', () => toggleShowAllHistory());
    }
    
    // Log refresh buttons
    const refreshSlurmctldBtn = document.getElementById('refresh-slurmctld-log-btn');
    if (refreshSlurmctldBtn) {
        refreshSlurmctldBtn.addEventListener('click', () => loadLog('slurmctld'));
    }
    
    const refreshSlurmdBtn = document.getElementById('refresh-slurmd-log-btn');
    if (refreshSlurmdBtn) {
        refreshSlurmdBtn.addEventListener('click', () => loadLog('slurmd'));
    }
    
    // Batch cancel button
    const batchCancelBtn = document.getElementById('batch-cancel-btn');
    if (batchCancelBtn) {
        batchCancelBtn.addEventListener('click', () => batchCancelJobs());
    }
}

// ==================== Log Loading ====================
async function loadLog(logType) {
    const outputId = logType === 'slurmctld' ? 'slurmctld-log-output' : 'slurmd-log-output';
    const output = document.getElementById(outputId);
    if (!output) return;
    
    output.textContent = '加载中...';
    
    try {
        const logPath = `/var/log/slurm/${logType}.log`;
        const response = await fetch(`/api/log?path=${encodeURIComponent(logPath)}`);
        const data = await response.json();
        
        if (data.content) {
            output.textContent = data.content;
        } else if (data.error) {
            output.textContent = `错误: ${data.error}`;
        } else {
            output.textContent = '无法加载日志';
        }
    } catch (error) {
        output.textContent = `加载失败: ${error.message}`;
    }
}

function toggleAutoRefresh(enable) {
    if (refreshInterval) clearInterval(refreshInterval);
    if (enable) {
        refreshInterval = setInterval(() => loadAllData(), 5000);
    }
}

// ==================== Data Loading ====================
async function loadAllData() {
    try {
        console.log('Loading data...');
        const response = await fetch('/api/allsystems');
        const data = await response.json();
        console.log('Data loaded:', data);
        updateAllData(data);
    } catch (error) {
        console.error('Failed to load data:', error);
    }
}

function updateAllData(data) {
    currentData = data;
    document.getElementById('last-update-time').textContent = new Date().toLocaleTimeString();
    
    updateDashboard(data.summary);
    updateNodesTable(data.nodes);
    updateJobsTables(data.jobs);
    updateGPUCards(data.gpus);
    updateGPUProcesses(data.gpu_processes);
    updateDashboardGPUDetails(data.gpus);
    updateUserStats(data.user_stats);
    updatePartitionStats(data.partition_stats);
    updatePartitionsInfo(data.partitions);
    updateCharts(data);
    
    // Update connection status
    const statusDot = document.getElementById('conn-status');
    const statusText = document.getElementById('conn-text');
    statusDot.classList.add('connected');
    statusText.textContent = '已连接';
}

// Dashboard GPU 详细信息 - 使用缩略图显示，8张一行
function updateDashboardGPUDetails(gpus) {
    const container = document.querySelector('#dashboard-gpu-section');
    if (!container) {
        // 如果容器不存在，创建一个
        const dashboardSection = document.querySelector('.dashboard-section');
        if (!dashboardSection) return;
        
        const gpuSection = document.createElement('div');
        gpuSection.id = 'dashboard-gpu-section';
        gpuSection.className = 'card';
        dashboardSection.appendChild(gpuSection);
    }
    
    const gpuContainer = document.querySelector('#dashboard-gpu-section');
    
    if (!gpus || gpus.length === 0) {
        gpuContainer.innerHTML = `
            <div class="card-header">
                <h3><i class="fas fa-microchip"></i> GPU 详细使用情况</h3>
            </div>
            <div class="card-body">
                <div style="text-align: center; padding: 30px; color: var(--text-secondary);">
                    未检测到 GPU
                </div>
            </div>
        `;
        return;
    }
    
    // 按节点分组统计
    const nodeStats = {};
    gpus.forEach(gpu => {
        const node = gpu.node || 'localhost';
        if (!nodeStats[node]) {
            nodeStats[node] = { total: 0, active: 0, temp: 0 };
        }
        nodeStats[node].total++;
        if (parseInt(gpu.utilization) > 0) nodeStats[node].active++;
        nodeStats[node].temp += parseInt(gpu.temperature) || 0;
    });
    
    const thumbnailsHtml = gpus.map(gpu => {
        const temp = parseInt(gpu.temperature) || 0;
        const tempClass = temp > 80 ? 'hot' : temp > 60 ? 'warm' : 'cool';
        const util = parseInt(gpu.utilization) || 0;
        const memUsed = parseInt(gpu.memory_used) || 0;
        const memTotal = parseInt(gpu.memory_total) || 1;
        const memPercent = Math.round((memUsed / memTotal) * 100);
        const node = gpu.node || 'localhost';
        const isActive = util > 0;
        
        return `
            <div class="gpu-thumbnail ${isActive ? 'active' : ''}" title="${gpu.name}
温度: ${temp}°C | 利用率: ${util}%
显存: ${memUsed}/${memTotal} MB (${memPercent}%)
功耗: ${gpu.power_draw !== 'N/A' ? gpu.power_draw + 'W' : 'N/A'}
节点: ${node}">
                <div class="gpu-thumbnail-header">GPU ${gpu.index}</div>
                <div class="gpu-thumbnail-temp ${tempClass}">${temp}°C</div>
                <div class="gpu-thumbnail-util" style="color: ${util > 80 ? 'var(--danger-color)' : util > 50 ? 'var(--warning-color)' : 'var(--success-color)'}">${util}%</div>
                <div class="gpu-thumbnail-mem">${memPercent}% 显存</div>
                <div class="gpu-thumbnail-node">${node}</div>
            </div>
        `;
    }).join('');
    
    // 生成节点统计摘要
    const nodeSummaryHtml = Object.entries(nodeStats).map(([node, stats]) => {
        const avgTemp = Math.round(stats.temp / stats.total);
        return `<span class="badge badge-primary" style="margin-right: 10px;">${node}: ${stats.active}/${stats.total} 活跃 | 平均温度 ${avgTemp}°C</span>`;
    }).join('');
    
    gpuContainer.innerHTML = `
        <div class="card-header">
            <h3><i class="fas fa-microchip"></i> GPU 详细使用情况</h3>
            <div>${nodeSummaryHtml}</div>
        </div>
        <div class="card-body" style="padding: 10px;">
            <div class="gpu-thumbnail-grid">
                ${thumbnailsHtml}
            </div>
        </div>
    `;
}

// ==================== Dashboard ====================
function updateDashboard(summary) {
    // Node stats
    document.getElementById('summary-nodes-total').textContent = summary.nodes.total;
    document.getElementById('summary-nodes-idle').textContent = summary.nodes.idle;
    document.getElementById('summary-nodes-alloc').textContent = summary.nodes.alloc;
    document.getElementById('summary-nodes-down').textContent = summary.nodes.down;
    document.getElementById('summary-nodes-mix').textContent = summary.nodes.mix;
    
    // Job stats
    document.getElementById('summary-jobs-total').textContent = summary.jobs.total;
    document.getElementById('summary-jobs-running').textContent = summary.jobs.running;
    document.getElementById('summary-jobs-pending').textContent = summary.jobs.pending;
    document.getElementById('summary-jobs-suspended').textContent = summary.jobs.suspended;
    
    // CPU stats
    document.getElementById('summary-cpus-total').textContent = summary.cpus.total;
    document.getElementById('summary-cpus-alloc').textContent = summary.cpus.alloc;
    document.getElementById('summary-cpus-idle').textContent = summary.cpus.idle;
    
    const cpuPercent = summary.cpus.total > 0 ? Math.round((summary.cpus.alloc / summary.cpus.total) * 100) : 0;
    document.getElementById('cpu-progress').style.width = `${cpuPercent}%`;
    document.getElementById('cpu-usage-percent').textContent = `${cpuPercent}%`;
    
    // GPU stats
    document.getElementById('summary-gpus-total').textContent = summary.gpus.total;
    document.getElementById('summary-gpus-alloc').textContent = summary.gpus.alloc;
    document.getElementById('summary-gpus-free').textContent = Math.max(0, summary.gpus.total - summary.gpus.alloc);
    
    const gpuPercent = summary.gpus.total > 0 ? Math.round((summary.gpus.alloc / summary.gpus.total) * 100) : 0;
    document.getElementById('gpu-progress').style.width = `${gpuPercent}%`;
    document.getElementById('gpu-usage-percent').textContent = `${gpuPercent}%`;
}

// ==================== Charts ====================
function updateCharts(data) {
    const summary = data.summary;
    
    // Update CSS Pie Chart - Nodes
    const nodesPie = document.getElementById('nodes-pie-chart');
    if (nodesPie) {
        const total = summary.nodes.idle + summary.nodes.alloc + summary.nodes.mix + summary.nodes.down;
        if (total > 0) {
            const idleDeg = (summary.nodes.idle / total) * 360;
            const allocDeg = idleDeg + (summary.nodes.alloc / total) * 360;
            const mixDeg = allocDeg + (summary.nodes.mix / total) * 360;
            nodesPie.style.setProperty('--idle-deg', idleDeg + 'deg');
            nodesPie.style.setProperty('--alloc-deg', allocDeg + 'deg');
            nodesPie.style.setProperty('--mix-deg', mixDeg + 'deg');
        }
        document.getElementById('nodes-idle-val').textContent = summary.nodes.idle;
        document.getElementById('nodes-alloc-val').textContent = summary.nodes.alloc;
        document.getElementById('nodes-mix-val').textContent = summary.nodes.mix;
        document.getElementById('nodes-down-val').textContent = summary.nodes.down;
    }
    
    // Update CSS Pie Chart - Jobs
    const jobsPie = document.getElementById('jobs-pie-chart');
    if (jobsPie) {
        const total = summary.jobs.total || 1;
        const other = Math.max(0, summary.jobs.total - summary.jobs.running - summary.jobs.pending - summary.jobs.suspended);
        const runningDeg = (summary.jobs.running / total) * 360;
        const pendingDeg = runningDeg + (summary.jobs.pending / total) * 360;
        const suspendedDeg = pendingDeg + (summary.jobs.suspended / total) * 360;
        jobsPie.style.setProperty('--idle-deg', runningDeg + 'deg');
        jobsPie.style.setProperty('--alloc-deg', pendingDeg + 'deg');
        jobsPie.style.setProperty('--mix-deg', suspendedDeg + 'deg');
        document.getElementById('jobs-running-val').textContent = summary.jobs.running;
        document.getElementById('jobs-pending-val').textContent = summary.jobs.pending;
        document.getElementById('jobs-suspended-val').textContent = summary.jobs.suspended;
        document.getElementById('jobs-other-val').textContent = other;
    }
    
    // Update CSS Pie Chart - CPU
    const cpuPie = document.getElementById('cpu-pie-chart');
    if (cpuPie) {
        const cpuTotal = summary.cpus.total || 1;
        const allocDeg = (summary.cpus.alloc / cpuTotal) * 360;
        cpuPie.style.setProperty('--cpu-alloc-deg', allocDeg + 'deg');
        document.getElementById('cpu-alloc-val').textContent = summary.cpus.alloc;
        document.getElementById('cpu-idle-val').textContent = summary.cpus.idle;
    }
    
    // Update User Charts
    const userStats = data.user_stats;
    const userNames = Object.keys(userStats);
    
    const userJobsContainer = document.getElementById('user-jobs-bars');
    if (userJobsContainer && userNames.length > 0) {
        const maxJobs = Math.max(...userNames.map(u => userStats[u].jobs), 1);
        userJobsContainer.innerHTML = userNames.map(user => {
            const jobs = userStats[user].jobs;
            const width = (jobs / maxJobs) * 100;
            return `<div class="hbar-item"><span class="hbar-label">${user}</span><div class="hbar-track"><div class="hbar-fill" style="width: ${width}%"></div></div></div>`;
        }).join('');
    }
    
    const userCpuContainer = document.getElementById('user-cpu-bars');
    if (userCpuContainer && userNames.length > 0) {
        const maxCpus = Math.max(...userNames.map(u => userStats[u].cpus), 1);
        userCpuContainer.innerHTML = userNames.map(user => {
            const cpus = userStats[user].cpus;
            const width = (cpus / maxCpus) * 100;
            return `<div class="hbar-item"><span class="hbar-label">${user}</span><div class="hbar-track"><div class="hbar-fill" style="width: ${width}%; background: linear-gradient(to right, #2ecc71, #27ae60)"></div></div></div>`;
        }).join('');
    }
}

// ==================== Nodes ====================
function updateNodesTable(nodes) {
    const tbody = document.querySelector('#nodes-table tbody');
    if (!tbody) return;
    
    tbody.innerHTML = nodes.map(node => {
        const stateClass = `state-${node.state.toLowerCase().replace(/[^a-z]/g, '')}`;
        return `<tr>
            <td><strong>${node.name}</strong></td>
            <td><span class="badge ${getStateBadgeClass(node.state)}">${STATE_LABELS[node.state] || node.state}</span></td>
            <td>${node.partition}</td>
            <td>${node.cpu_alloc || 'N/A'}</td>
            <td>${formatMemory(node.memory)}</td>
            <td>${formatMemory(node.free_mem)}</td>
            <td>${node.load || 'N/A'}</td>
            <td>${node.gres}</td>
            <td><button class="action-btn" onclick="showNodeDetail('${node.name}')">👁️</button></td>
        </tr>`;
    }).join('');
}

async function showNodeDetail(nodeName) {
    try {
        const response = await fetch(`/api/node/${nodeName}`);
        const data = await response.json();
        document.getElementById('modal-node-name').textContent = nodeName;
        document.getElementById('node-detail-content').innerHTML = Object.entries(data).map(([key, value]) => 
            `<div class="detail-item"><div class="detail-label">${key}</div><div class="detail-value">${value}</div></div>`
        ).join('');
        document.getElementById('node-modal').classList.add('active');
    } catch (error) {
        alert('加载节点详情失败');
    }
}

// ==================== Jobs ====================
function updateJobsTables(jobs) {
    const tbody = document.querySelector('#jobs-table tbody');
    if (tbody) {
        tbody.innerHTML = jobs.map(job => {
            // Parse GPU info from gres
            let gpuInfo = '-';
            if (job.gres && job.gres !== 'none') {
                const gpuMatch = job.gres.match(/gpu:(\d+)/);
                if (gpuMatch) {
                    gpuInfo = `GPU x${gpuMatch[1]}`;
                } else if (job.gres.includes('gpu')) {
                    gpuInfo = 'GPU';
                }
            }
            
            return `<tr>
            <td><input type="checkbox" class="job-checkbox" value="${job.job_id}"></td>
            <td>${job.job_id}</td>
            <td>${job.name}</td>
            <td>${job.user}</td>
            <td>${job.partition}</td>
            <td><span class="badge ${getJobBadgeClass(job.state)}">${STATE_LABELS[job.state] || job.state}</span></td>
            <td>${job.nodes}</td>
            <td>${job.nodelist}</td>
            <td>${job.cpus}</td>
            <td>${job.memory}</td>
            <td>${gpuInfo}</td>
            <td>${job.priority}</td>
            <td>${job.time}</td>
            <td><button class="action-btn" onclick="showJobDetail('${job.job_id}')">👁️</button> <button class="action-btn danger" onclick="cancelJob('${job.job_id}')">❌</button></td>
        </tr>`}).join('');
    }
    
    // Dashboard tables
    const runningTbody = document.querySelector('#running-jobs-table tbody');
    if (runningTbody) {
        const runningJobs = jobs.filter(j => j.state === 'R').slice(0, 5);
        runningTbody.innerHTML = runningJobs.map(job => `<tr>
            <td>${job.job_id}</td><td>${job.name}</td><td>${job.user}</td><td>${job.partition}</td>
            <td>${job.nodes}</td><td>${job.cpus}</td><td><span class="badge badge-success">运行中</span></td><td>${job.time}</td>
        </tr>`).join('') || '<tr><td colspan="8">暂无运行中的作业</td></tr>';
    }
    
    const pendingTbody = document.querySelector('#pending-jobs-table tbody');
    if (pendingTbody) {
        const pendingJobs = jobs.filter(j => j.state === 'PD').slice(0, 5);
        pendingTbody.innerHTML = pendingJobs.map(job => `<tr>
            <td>${job.job_id}</td><td>${job.name}</td><td>${job.user}</td><td>${job.partition}</td>
            <td>${job.priority}</td><td>${job.start_time}</td>
        </tr>`).join('') || '<tr><td colspan="6">暂无等待中的作业</td></tr>';
    }
}

async function showJobDetail(jobId) {
    try {
        const response = await fetch(`/api/job/${jobId}`);
        const data = await response.json();
        document.getElementById('modal-job-id').textContent = jobId;
        document.getElementById('job-detail-content').innerHTML = Object.entries(data).map(([key, value]) => 
            `<div class="detail-item ${value.length > 50 ? 'full-width' : ''}"><div class="detail-label">${key}</div><div class="detail-value">${value}</div></div>`
        ).join('');
        document.getElementById('job-modal').classList.add('active');
    } catch (error) {
        alert('加载作业详情失败');
    }
}

async function cancelJob(jobId) {
    if (!confirm(`确定要取消作业 ${jobId} 吗？`)) return;
    
    // Check if password verification is needed
    try {
        const configResponse = await fetch('/api/app-config');
        const config = await configResponse.json();
        
        if (config.password_enabled) {
            // Show password modal
            pendingCancelJobId = jobId;
            pendingCancelJobs = [];  // Clear batch jobs
            showPasswordModal();
            return;
        }
        
        // No password needed, proceed directly
        await doCancelJob(jobId, null);
    } catch (error) {
        console.error('Failed to check config:', error);
        alert('操作失败');
    }
}

async function doCancelJob(jobId, password) {
    try {
        const response = await fetch(`/api/job/${jobId}/cancel`, { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: password })
        });
        const data = await response.json();
        
        if (response.status === 403) {
            alert('密码错误，操作被拒绝');
            return false;
        }
        
        alert(data.success ? '作业已取消' : `失败: ${data.message}`);
        loadAllData();
        return data.success;
    } catch (error) {
        alert('操作失败');
        return false;
    }
}

function showPasswordModal() {
    document.getElementById('password-modal').classList.add('active');
    document.getElementById('admin-password').value = '';
    document.getElementById('admin-password').focus();
}

function closePasswordModal() {
    document.getElementById('password-modal').classList.remove('active');
    pendingCancelJobId = null;
    pendingCancelJobs = [];
}

async function confirmCancelWithPassword() {
    const password = document.getElementById('admin-password').value;
    
    if (!password) {
        alert('请输入密码');
        return;
    }
    
    // Verify password first
    try {
        const verifyResponse = await fetch('/api/verify-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: password })
        });
        
        if (!verifyResponse.ok) {
            alert('密码错误');
            return;
        }
        
        // Password verified, proceed with cancellation
        // Save IDs before closing modal (which clears them)
        const jobIdToCancel = pendingCancelJobId;
        const jobsToCancel = [...pendingCancelJobs];
        
        closePasswordModal();
        
        if (jobIdToCancel) {
            // Single job cancel
            await doCancelJob(jobIdToCancel, password);
        } else if (jobsToCancel.length > 0) {
            // Batch cancel
            let successCount = 0;
            for (const jobId of jobsToCancel) {
                const success = await doCancelJob(jobId, password);
                if (success) successCount++;
            }
            alert(`批量操作完成：成功取消 ${successCount}/${jobsToCancel.length} 个作业`);
            document.getElementById('select-all-jobs').checked = false;
        }
    } catch (error) {
        alert('验证失败');
    }
}

async function batchCancelJobs() {
    const selected = Array.from(document.querySelectorAll('.job-checkbox:checked')).map(cb => cb.value);
    if (selected.length === 0) {
        alert('请选择要取消的作业');
        return;
    }
    if (!confirm(`确定要取消 ${selected.length} 个作业吗？`)) return;
    
    // Check if password verification is needed
    try {
        const configResponse = await fetch('/api/app-config');
        const config = await configResponse.json();
        
        if (config.password_enabled) {
            // Show password modal
            pendingCancelJobId = null;
            pendingCancelJobs = selected;
            showPasswordModal();
            return;
        }
        
        // No password needed, proceed directly
        let successCount = 0;
        for (const jobId of selected) {
            const success = await doCancelJob(jobId, null);
            if (success) successCount++;
        }
        alert(`批量操作完成：成功取消 ${successCount}/${selected.length} 个作业`);
        document.getElementById('select-all-jobs').checked = false;
    } catch (error) {
        console.error('Failed to check config:', error);
        alert('操作失败');
    }
}

// ==================== GPU ====================
function updateGPUCards(gpus) {
    const container = document.getElementById('gpu-cards');
    if (!container) return;
    
    if (!gpus || gpus.length === 0) {
        container.innerHTML = '<div class="card"><div class="card-header"><h3>未检测到 NVIDIA GPU</h3></div></div>';
        return;
    }
    
    // 按节点分组
    const nodeGroups = {};
    gpus.forEach(gpu => {
        const node = gpu.node || 'localhost';
        if (!nodeGroups[node]) {
            nodeGroups[node] = [];
        }
        nodeGroups[node].push(gpu);
    });
    
    // 生成按节点分组的HTML
    container.innerHTML = Object.entries(nodeGroups).map(([node, nodeGpus], groupIndex) => {
        // 计算节点统计信息
        const totalGpus = nodeGpus.length;
        const activeGpus = nodeGpus.filter(g => parseInt(g.utilization) > 0).length;
        const avgTemp = Math.round(nodeGpus.reduce((sum, g) => sum + (parseInt(g.temperature) || 0), 0) / totalGpus);
        const totalMem = nodeGpus.reduce((sum, g) => sum + (parseInt(g.memory_total) || 0), 0);
        const usedMem = nodeGpus.reduce((sum, g) => sum + (parseInt(g.memory_used) || 0), 0);
        const memPercent = Math.round((usedMem / totalMem) * 100);
        
        // 温度样式
        const tempClass = avgTemp > 80 ? 'hot' : avgTemp > 60 ? 'warm' : 'cool';
        const tempColor = avgTemp > 80 ? 'var(--danger-color)' : avgTemp > 60 ? 'var(--warning-color)' : 'var(--success-color)';
        
        // 生成节点内GPU卡片
        const gpuCardsHtml = nodeGpus.map(gpu => {
            const util = parseInt(gpu.utilization) || 0;
            const memUsed = parseInt(gpu.memory_used) || 0;
            const memTotal = parseInt(gpu.memory_total) || 1;
            const gpuMemPercent = Math.round((memUsed / memTotal) * 100);
            const temp = parseInt(gpu.temperature) || 0;
            const gpuTempClass = temp > 80 ? 'hot' : temp > 60 ? 'warm' : 'cool';
            
            return `
                <div class="gpu-detail-card">
                    <div class="gpu-detail-header">
                        <div class="gpu-detail-name">
                            <i class="fas fa-microchip text-success"></i>
                            GPU ${gpu.index}
                        </div>
                        <div class="gpu-detail-temp ${gpuTempClass}">${temp}°C</div>
                    </div>
                    <div class="gpu-stats">
                        <div class="gpu-stat">
                            <div class="gpu-stat-label">利用率</div>
                            <div class="gpu-stat-value" style="color: ${util > 80 ? 'var(--danger-color)' : util > 50 ? 'var(--warning-color)' : 'var(--success-color)'}">${util}%</div>
                        </div>
                        <div class="gpu-stat">
                            <div class="gpu-stat-label">显存</div>
                            <div class="gpu-stat-value">${Math.round(memUsed/1024)}G/${Math.round(memTotal/1024)}G</div>
                        </div>
                    </div>
                    <div class="progress-bar" style="margin-bottom: 6px;">
                        <div class="progress-fill gpu" style="width: ${util}%"></div>
                    </div>
                    <div class="progress-bar" style="margin-bottom: 10px;">
                        <div class="progress-fill" style="width: ${gpuMemPercent}%"></div>
                    </div>
                    <div class="gpu-info">
                        <span>功耗: ${gpu.power_draw !== 'N/A' ? gpu.power_draw + 'W' : 'N/A'}</span>
                        <span>${gpu.name.split(' ').pop()}</span>
                    </div>
                </div>
            `;
        }).join('');
        
        return `
            <div class="gpu-node-group ${groupIndex === 0 ? 'expanded' : ''}" data-node="${node}">
                <div class="gpu-node-header" onclick="toggleGPUNodeGroup(this)">
                    <div class="gpu-node-title">
                        <i class="fas fa-server text-primary"></i>
                        <span class="gpu-node-name">${node}</span>
                        <div class="gpu-node-stats">
                            <div class="gpu-node-stat">
                                <i class="fas fa-microchip"></i>
                                <span>GPU: <span class="gpu-node-stat-value">${activeGpus}/${totalGpus}</span> 活跃</span>
                            </div>
                            <div class="gpu-node-stat">
                                <i class="fas fa-thermometer-half"></i>
                                <span>平均温度: <span class="gpu-node-stat-value" style="color: ${tempColor}">${avgTemp}°C</span></span>
                            </div>
                            <div class="gpu-node-stat">
                                <i class="fas fa-memory"></i>
                                <span>显存: <span class="gpu-node-stat-value">${memPercent}%</span></span>
                            </div>
                        </div>
                    </div>
                    <div class="gpu-node-toggle">
                        <i class="fas fa-chevron-down"></i>
                    </div>
                </div>
                <div class="gpu-node-content">
                    <div class="gpu-node-cards">
                        ${gpuCardsHtml}
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// 切换GPU节点组展开/折叠
function toggleGPUNodeGroup(header) {
    const group = header.closest('.gpu-node-group');
    group.classList.toggle('expanded');
}

function updateGPUProcesses(processes) {
    const tbody = document.querySelector('#gpu-processes-table tbody');
    if (!tbody) return;
    
    tbody.innerHTML = processes.map(proc => {
        const node = proc.node || 'localhost';
        return `<tr>
            <td><span class="badge badge-primary">${node}</span></td>
            <td>${proc.gpu_id}</td>
            <td>${proc.pid}</td>
            <td>${proc.type}</td>
            <td>${proc.sm}%</td>
            <td>${proc.mem}%</td>
            <td>${proc.enc}</td>
            <td>${proc.dec}</td>
            <td>${proc.command}</td>
        </tr>`;
    }).join('') || '<tr><td colspan="9" style="text-align: center;">无GPU进程</td></tr>';
}

// ==================== Users ====================
function updateUserStats(userStats) {
    const tbody = document.querySelector('#users-table tbody');
    if (!tbody) return;
    
    const users = Object.entries(userStats).sort((a, b) => b[1].jobs - a[1].jobs);
    tbody.innerHTML = users.map(([user, stats]) => `<tr>
        <td><strong>${user}</strong></td><td>${stats.jobs}</td><td>${stats.running}</td>
        <td>${stats.pending}</td><td>${stats.suspended}</td><td>${stats.cpus}</td>
    </tr>`).join('') || '<tr><td colspan="6">无用户数据</td></tr>';
}

// ==================== Config ====================
async function loadConfig() {
    try {
        const response = await fetch('/api/app-config');
        const data = await response.json();
        
        // Basic settings
        const basicConfig = document.getElementById('basic-config');
        if (basicConfig && data.settings) {
            const basicSettings = ['clustername', 'slurmctldhost', 'slurmuser', 'selecttype', 'schedulertype'];
            basicConfig.innerHTML = basicSettings
                .filter(key => data.settings[key])
                .map(key => `<div class="config-item"><div class="config-item-label">${key}</div><div class="config-item-value">${data.settings[key]}</div></div>`)
                .join('');
        }
        
        // Nodes config
        const nodesConfig = document.getElementById('nodes-config');
        if (nodesConfig && data.nodes) {
            nodesConfig.innerHTML = data.nodes.map(node => 
                `<div class="config-node">NodeName=${node.nodename} CPUs=${node.cpus} RealMemory=${node.realmemory} Gres=${node.gres || 'none'} State=${node.state}</div>`
            ).join('');
        }
        
        // Partitions config
        const partitionsConfig = document.getElementById('partitions-config');
        if (partitionsConfig && data.partitions) {
            partitionsConfig.innerHTML = data.partitions.map(part => 
                `<div class="config-partition">PartitionName=${part.partitionname} Nodes=${part.nodes} Default=${part.default || 'NO'} MaxTime=${part.maxtime || 'N/A'} State=${part.state}</div>`
            ).join('');
        }
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

// ==================== Statistics ====================
async function loadStatistics() {
    try {
        // Get time range
        const timeRange = document.getElementById('stats-time-range')?.value || 168;
        const hours = parseInt(timeRange);
        
        // 1. Load Job Stats
        const jobStatsResponse = await fetch(`/api/stats/jobs?hours=${hours}`);
        const jobStats = await jobStatsResponse.json();
        
        // Update job stats cards
        document.getElementById('stats-completed').textContent = jobStats.completed;
        document.getElementById('stats-failed').textContent = jobStats.failed;
        document.getElementById('stats-total').textContent = jobStats.total;
        document.getElementById('stats-cpu-hours').textContent = Math.round(jobStats.total_cpu_hours);
        
        // 2. Load User Rankings
        const userRankResponse = await fetch(`/api/stats/users/top?days=${Math.ceil(hours/24)}&top=10`);
        const userRankData = await userRankResponse.json();
        
        // Sort by CPU time
        const byCpuTime = [...userRankData].sort((a, b) => parseFloat(b.cpu_time) - parseFloat(a.cpu_time));
        const byJobs = [...userRankData].sort((a, b) => parseInt(b.jobs) - parseInt(a.jobs));
        
        // Update user rank tables
        const cpuRankTbody = document.querySelector('#user-rank-cpu-table tbody');
        if (cpuRankTbody) {
            cpuRankTbody.innerHTML = byCpuTime.slice(0, 10).map((user, idx) => `
                <tr>
                    <td><span class="rank-badge rank-${idx < 3 ? idx + 1 : ''}">${idx + 1}</span></td>
                    <td><strong>${user.login}</strong></td>
                    <td>${user.cpu_time} 小时</td>
                    <td>${user.jobs}</td>
                </tr>
            `).join('') || '<tr><td colspan="4">无数据</td></tr>';
        }
        
        const jobsRankTbody = document.querySelector('#user-rank-jobs-table tbody');
        if (jobsRankTbody) {
            jobsRankTbody.innerHTML = byJobs.slice(0, 10).map((user, idx) => `
                <tr>
                    <td><span class="rank-badge rank-${idx < 3 ? idx + 1 : ''}">${idx + 1}</span></td>
                    <td><strong>${user.login}</strong></td>
                    <td>${user.jobs}</td>
                    <td>${user.cpu_time} 小时</td>
                </tr>
            `).join('') || '<tr><td colspan="4">无数据</td></tr>';
        }
        
        // 3. Load Partition Analysis
        const partitionBars = document.getElementById('partition-bars');
        if (partitionBars && jobStats.partitions) {
            const partitions = Object.entries(jobStats.partitions).sort((a, b) => b[1].jobs - a[1].jobs);
            const maxJobs = Math.max(...partitions.map(p => p[1].jobs), 1);
            
            partitionBars.innerHTML = partitions.map(([name, data]) => {
                const width = (data.jobs / maxJobs) * 100;
                return `
                    <div class="partition-bar-item">
                        <span class="partition-bar-label">${name}</span>
                        <div class="partition-bar-track">
                            <div class="partition-bar-fill" style="width: ${width}%">${data.jobs}</div>
                        </div>
                    </div>
                `;
            }).join('') || '<p>无分区数据</p>';
        }
        
        // 4. Load Node Utilization
        const nodeStatsResponse = await fetch('/api/stats/nodes');
        const nodeStats = await nodeStatsResponse.json();
        
        const nodeUtilTbody = document.querySelector('#node-util-table tbody');
        if (nodeUtilTbody) {
            nodeUtilTbody.innerHTML = nodeStats.map(node => {
                const cpus = node.cpus ? node.cpus.split('/') : ['0', '0', '0', '0'];
                const alloc = parseInt(cpus[0]) || 0;
                const total = parseInt(cpus[3]) || 1;
                const util = Math.round((alloc / total) * 100);
                const utilClass = util < 50 ? 'low' : util < 80 ? 'medium' : 'high';
                
                return `<tr>
                    <td><strong>${node.name}</strong></td>
                    <td><span class="badge ${getStateBadgeClass(node.state)}">${STATE_LABELS[node.state] || node.state}</span></td>
                    <td>${node.cpus || 'N/A'}</td>
                    <td>${node.load || 'N/A'}</td>
                    <td>
                        <div class="utilization-bar">
                            <div class="utilization-fill ${utilClass}" style="width: ${util}%"></div>
                        </div>
                        <span style="font-size: 11px; color: var(--text-secondary);">${util}%</span>
                    </td>
                </tr>`;
            }).join('') || '<tr><td colspan="5">无节点数据</td></tr>';
        }
        
        // 5. Load Wait Times
        const waitTimesResponse = await fetch('/api/stats/wait-times');
        const waitTimes = await waitTimesResponse.json();
        
        const waitTimeTbody = document.querySelector('#wait-time-table tbody');
        if (waitTimeTbody) {
            waitTimeTbody.innerHTML = waitTimes.slice(0, 20).map(wt => {
                const hours = Math.floor(wt.wait_minutes / 60);
                const mins = Math.round(wt.wait_minutes % 60);
                const timeStr = hours > 0 ? `${hours}小时${mins}分` : `${mins}分钟`;
                return `<tr>
                    <td>${wt.job_id}</td>
                    <td>${timeStr}</td>
                </tr>`;
            }).join('') || '<tr><td colspan="2">无等待中的作业</td></tr>';
        }
        
        // 6. Load Job History (default 30 records)
        const historyResponse = await fetch(`/api/history/jobs?hours=${hours}&limit=30`);
        const historyData = await historyResponse.json();
        historyDataAll = historyData;  // Store for filtering
        historyShowAll = false;
        
        renderHistoryTable(historyData);
        
        // Setup history filters
        setupHistoryFilters(historyData);
        
        // 7. Load sdiag (scheduler stats)
        const diagResponse = await fetch('/api/diag');
        const diagData = await diagResponse.json();
        
        // 8. Load user resource usage (CPU/GPU time)
        const userResourceResponse = await fetch(`/api/user-resource-usage?hours=${hours}`);
        const userResourceResult = await userResourceResponse.json();
        const userResourceData = userResourceResult.users || [];
        const totalCpuMinutes = userResourceResult.total_cpu_minutes || 0;
        const totalGpuMinutes = userResourceResult.total_gpu_minutes || 0;
        
        const diagContent = document.getElementById('diag-content');
        if (diagContent) {
            let html = '';
            
            if (diagData.scheduler && Object.keys(diagData.scheduler).length > 0) {
                html += '<div class="stats-section"><h4>调度器统计</h4><div class="stats-grid">';
                Object.entries(diagData.scheduler).forEach(([key, value]) => {
                    html += `<div class="stats-item"><div class="stats-item-label">${key}</div><div class="stats-item-value">${value}</div></div>`;
                });
                html += '</div></div>';
            }
            
            // User Resource Usage (CPU/GPU time)
            if (userResourceData && userResourceData.length > 0) {
                html += '<div class="stats-section"><h4>用户资源使用情况 (单位: 分钟)</h4>';
                html += `<div style="margin-bottom: 10px; color: var(--text-secondary); font-size: 12px;">
                    总计: CPU核时 ${totalCpuMinutes} 分钟 | GPU核时 ${totalGpuMinutes} 分钟
                </div>`;
                html += '<div class="user-resource-table-container"><table class="user-resource-table">';
                html += '<thead><tr><th>用户</th><th>作业数</th><th>CPU所用核时</th><th>占比</th><th>调用GPU的作业数</th><th>GPU所用核时</th><th>占比</th></tr></thead>';
                html += '<tbody>';
                userResourceData.forEach(user => {
                    const cpuPercentBar = user.cpu_percent > 0 
                        ? `<div class="percent-bar"><div class="percent-fill cpu" style="width: ${Math.min(user.cpu_percent, 100)}%"></div><span>${user.cpu_percent}%</span></div>` 
                        : '-';
                    const gpuPercentBar = user.gpu_percent > 0 
                        ? `<div class="percent-bar"><div class="percent-fill gpu" style="width: ${Math.min(user.gpu_percent, 100)}%"></div><span>${user.gpu_percent}%</span></div>` 
                        : '-';
                    
                    html += `<tr>
                        <td><strong>${user.user}</strong></td>
                        <td>${user.jobs}</td>
                        <td><span style="color: #3498db; font-weight: 600;">${user.cpu_minutes}</span></td>
                        <td>${cpuPercentBar}</td>
                        <td>${user.gpu_jobs > 0 ? '<span style="color: #2ecc71; font-weight: 600;">' + user.gpu_jobs + '</span>' : '-'}</td>
                        <td>${user.gpu_minutes > 0 ? '<span style="color: #e74c3c; font-weight: 600;">' + user.gpu_minutes + '</span>' : '-'}</td>
                        <td>${gpuPercentBar}</td>
                    </tr>`;
                });
                html += '</tbody></table></div></div>';
            }
            
            diagContent.innerHTML = html || '<p>暂无调度器统计信息</p>';
        }
        

        
    } catch (error) {
        console.error('Failed to load statistics:', error);
    }
}

function setupHistoryFilters(historyData) {
    const userFilter = document.getElementById('history-user-filter');
    const stateFilter = document.getElementById('history-state-filter');
    
    if (userFilter) {
        userFilter.addEventListener('input', () => filterHistory(historyData));
    }
    if (stateFilter) {
        stateFilter.addEventListener('input', () => filterHistory(historyData));
    }
}

function renderHistoryTable(data, showLimit = null) {
    const historyTbody = document.querySelector('#job-history-table tbody');
    if (!historyTbody) return;
    
    // Determine how many records to show
    const limit = historyShowAll ? (showLimit || data.length) : Math.min(30, data.length);
    const displayData = data.slice(0, limit);
    
    historyTbody.innerHTML = displayData.map(job => `
        <tr>
            <td>${job.job_id}</td>
            <td>${job.name}</td>
            <td>${job.user}</td>
            <td>${job.partition}</td>
            <td><span class="badge ${getJobBadgeClass(job.state)}">${STATE_LABELS[job.state] || job.state}</span></td>
            <td>${job.exit_code}</td>
            <td>${job.start}</td>
            <td>${job.end}</td>
            <td>${job.elapsed}</td>
            <td>${job.cpu_time}</td>
        </tr>
    `).join('') || '<tr><td colspan="10">无历史记录</td></tr>';
    
    // Update button text to show count
    const showAllBtn = document.getElementById('show-all-history-btn');
    if (showAllBtn) {
        if (historyShowAll) {
            showAllBtn.innerHTML = `📊 显示简要 (共${data.length}条)`;
        } else {
            showAllBtn.innerHTML = `📊 显示全部 (${data.length}条)`;
        }
    }
}

async function toggleShowAllHistory() {
    const showAllBtn = document.getElementById('show-all-history-btn');
    if (!showAllBtn) return;
    
    if (!historyShowAll) {
        // Load all data
        showAllBtn.innerHTML = '🔄 加载中...';
        const timeRange = document.getElementById('stats-time-range')?.value || 168;
        const hours = parseInt(timeRange);
        
        try {
            const historyResponse = await fetch(`/api/history/jobs?hours=${hours}`);
            const allData = await historyResponse.json();
            historyDataAll = allData;
            historyShowAll = true;
            renderHistoryTable(allData);
        } catch (error) {
            console.error('Failed to load all history:', error);
            showAllBtn.innerHTML = '❌ 加载失败';
        }
    } else {
        // Switch back to limited view (reload with limit)
        const timeRange = document.getElementById('stats-time-range')?.value || 168;
        const hours = parseInt(timeRange);
        
        try {
            const historyResponse = await fetch(`/api/history/jobs?hours=${hours}&limit=30`);
            const limitedData = await historyResponse.json();
            historyDataAll = limitedData;
            historyShowAll = false;
            renderHistoryTable(limitedData);
        } catch (error) {
            console.error('Failed to load limited history:', error);
        }
    }
}

function filterHistory(historyData) {
    const userTerm = document.getElementById('history-user-filter')?.value.toLowerCase() || '';
    const stateTerm = document.getElementById('history-state-filter')?.value.toUpperCase() || '';
    
    const filtered = historyData.filter(job => {
        const matchUser = !userTerm || job.user.toLowerCase().includes(userTerm);
        const matchState = !stateTerm || job.state.toUpperCase().includes(stateTerm);
        return matchUser && matchState;
    });
    
    renderHistoryTable(filtered);
}

// ==================== Partitions ====================
function updatePartitionsInfo(partitions) {
    const grid = document.getElementById('partitions-grid');
    if (!grid) return;
    
    grid.innerHTML = partitions.map(part => `<div class="partition-card">
        <div class="partition-header">
            <span class="partition-name">${part.partitionname || 'N/A'}</span>
            <span class="partition-status ${(part.state || '').toLowerCase()}">${part.state || 'UNKNOWN'}</span>
        </div>
        <div class="partition-details">
            <p><strong>节点:</strong> ${part.nodes || 'N/A'}</p>
            <p><strong>默认:</strong> ${part.default === 'YES' ? '是' : '否'}</p>
            <p><strong>最大时间:</strong> ${part.maxtime || 'N/A'}</p>
        </div>
    </div>`).join('');
}

function updatePartitionStats(stats) {
    const tbody = document.querySelector('#partition-stats-table tbody');
    if (!tbody) return;
    
    const partitions = Object.entries(stats);
    tbody.innerHTML = partitions.map(([name, stat]) => `<tr>
        <td><strong>${name}</strong></td><td>${stat.running}</td><td>${stat.pending}</td><td>${stat.total}</td>
    </tr>`).join('') || '<tr><td colspan="4">无分区数据</td></tr>';
}

// ==================== Helpers ====================
function formatMemory(mb) {
    if (!mb || mb === 'N/A' || mb === '') return 'N/A';
    const num = parseInt(mb);
    if (isNaN(num)) return mb;
    if (num >= 1024 * 1024) return `${(num / 1024 / 1024).toFixed(2)} TB`;
    if (num >= 1024) return `${(num / 1024).toFixed(2)} GB`;
    return `${num} MB`;
}

function getStateBadgeClass(state) {
    const stateLower = state.toLowerCase();
    if (stateLower.includes('idle')) return 'badge-success';
    if (stateLower.includes('alloc')) return 'badge-warning';
    if (stateLower.includes('mix')) return 'badge-info';
    if (stateLower.includes('down') || stateLower.includes('drain') || stateLower.includes('fail')) return 'badge-danger';
    return 'badge-primary';
}

function getJobBadgeClass(state) {
    switch (state) {
        case 'R': return 'badge-success';
        case 'PD': return 'badge-warning';
        case 'S': case 'ST': return 'badge-info';
        case 'CG': return 'badge-primary';
        default: return 'badge-danger';
    }
}

function filterTables(term) {
    document.querySelectorAll('table tbody tr').forEach(row => {
        row.style.display = row.textContent.toLowerCase().includes(term) ? '' : 'none';
    });
}

// Expose functions to global scope
window.showNodeDetail = showNodeDetail;
window.showJobDetail = showJobDetail;
window.cancelJob = cancelJob;
