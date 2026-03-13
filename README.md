# Slurm 集群监控系统 v1.5.0

一个功能全面的 Web 版 Slurm 作业调度系统监控面板，支持 **Socket.IO 实时更新**。

> 📖 **文档导航**:
> - [README_DETAILED.md](README_DETAILED.md) - 功能详细介绍
> - [USER_GUIDE.md](USER_GUIDE.md) - **完整使用指南（推荐）**

## 功能特性

### 仪表盘
- 实时节点状态概览（总数/空闲/已分配/故障/混合）
- 作业状态统计（总数/运行中/等待中/暂停）
- CPU 资源使用情况（总核心/已分配/空闲）
- GPU 资源监控
- CSS 饼图可视化（无需外部依赖）

### 节点监控
- 所有节点详细信息表格
- 节点状态筛选和搜索
- **节点详情抽屉** - 点击节点名查看详细信息
- 节点管理操作（drain/resume）
- **资源预留管理** - 创建/删除节点预留

### 作业管理
- 完整的作业队列展示
- 按状态、分区筛选
- 批量操作（取消、挂起、释放、暂停、恢复）
- **作业详情抽屉** - 点击作业ID查看详细信息
- **密码验证保护敏感操作**

### GPU 监控
- GPU 温度和利用率
- 显存使用情况
- GPU 进程列表
- 多 GPU 支持

### 用户统计
- 各用户作业数量
- CPU 使用量排行
- **用户资源使用情况（CPU/GPU 核时 + 占比）**
- 可视化图表展示

### 分区信息
- 分区配置详情
- 分区作业统计
- 分区状态监控

### 磁盘配额 ⭐ 新增
- 用户磁盘配额监控（使用 `repquota -avus`）
- 显示已用空间、软限制、硬限制
- 超限/接近软限状态提醒
- 支持按状态筛选

### 组织拓扑 ⭐ 新增
- **QOS/账户/用户关系可视化** - 独立的组织拓扑页面
- **思维导图布局** - 使用 SVG 曲线展示层级关系
- **三层结构** - QOS → 账户 → 用户
- **资源配额信息** - 鼠标悬停显示组资源、最大资源、最大时长等
- **数据准确性** - 从 `sacctmgr list associations tree` 命令获取，保证层级关系准确

### 统计报表 ⭐ 核心功能
- **调度器统计**
- **用户资源使用详情** - 显示每个用户的 CPU/GPU 核时及占比
- 用户排行（按 CPU 时间/作业数）
- 分区使用分析
- 节点利用率报表
- 作业等待时间
- **历史作业记录**（支持分页加载）

### 系统配置
- Slurm 配置文件查看
- 节点配置详情
- 分区配置详情
- **管理员密码设置**

### 日志诊断
- slurmctld 日志（最后 100 行）
- slurmd 日志（最后 100 行）
- 实时刷新

### Web Shell ⭐ 新增功能
- **基于 Web 的终端访问** - 通过浏览器访问系统 Shell
- **系统用户认证** - 使用 SSH 登录相同的用户名密码
- **XTerm.js 终端仿真** - 支持颜色、光标、清屏等终端特性
- **实时双向通信** - 使用 WebSocket 传输数据
- **快捷键支持** - Ctrl+C、Ctrl+D、Tab 补全等
- **安全会话管理** - 30分钟超时自动退出

### 实时更新 (Socket.IO)
- **Socket.IO 双向实时通信**
- 5秒自动刷新
- 连接状态指示（实时/轮询）
- 自动重连机制

---

## 用户资源使用详情 ⭐

系统的核心分析功能，展示每个用户的资源消耗详情：

**显示效果示例：**

```
总计: CPU核时 15234.5 分钟 | GPU核时 3456.2 分钟

| 用户    | 作业数 | CPU所用核时 | 占比    | 调用GPU的作业数 | GPU所用核时 | 占比   |
|---------|--------|-------------|---------|-----------------|-------------|--------|
| user1   | 25     | 5234.5      | ████34.4% | 5               | 1234.5      | ████35.7% |
| user2   | 15     | 3123.2      | ████20.5% | -               | -           | -      |
| user3   | 30     | 2876.8      | ████18.9% | 3               | 987.3       | ████28.6% |
```

**数据说明：**
- **CPU所用核时**: `CPU核心数 × 运行时间(分钟)`
- **GPU所用核时**: `GPU卡数 × 运行时间(分钟)`
- **占比**: 该用户使用量占全集群总数的百分比
- **进度条**: 蓝色表示 CPU 占比，红色表示 GPU 占比

---

## 安装部署

### 方式一：直接运行

```bash
cd /root/slurm-web
./start.sh
```

访问 http://localhost:5000

### 方式二：Systemd 服务

```bash
# 安装服务
sudo ./install.sh

# 启动服务
sudo systemctl start slurm-monitor

# 查看状态
sudo systemctl status slurm-monitor
```

### 方式三：生产环境部署（Gunicorn + Gevent）

```bash
# 安装依赖
pip3 install gunicorn gevent gevent-websocket

# 使用 gunicorn 运行（支持 WebSocket）
gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 -b 0.0.0.0:5000 app:app
```

---

## API 接口

### 登录接口

- `GET /login` - 登录页面
- `POST /api/login` - 用户登录（支持 admin/user 类型）
- `POST /api/logout` - 退出登录
- `GET /api/current-user` - 获取当前登录用户信息
- `POST /api/check-first-login` - 检查是否首次登录

### 数据获取接口

- `GET /api/summary` - 集群概览
- `GET /api/nodes` - 节点列表
- `GET /api/node/<name>` - 节点详情
- `GET /api/jobs` - 作业列表
- `GET /api/job/<id>` - 作业详情
- `GET /api/partitions` - 分区列表
- `GET /api/gpus` - GPU 信息
- `GET /api/gpu-processes` - GPU 进程
- `GET /api/user-stats` - 用户统计
- `GET /api/user-resource-usage?hours=24` - 用户资源使用（CPU/GPU 核时）
- `GET /api/partition-stats` - 分区统计
- `GET /api/config` - Slurm 配置
- `GET /api/diag` - 调度器诊断
- `GET /api/history/jobs?hours=24&limit=30` - 历史作业（支持限制条数）
- `GET /api/allsystems` - 所有数据
- `GET /api/announcements` - 获取公告列表

### Socket.IO 事件

- `connect` - 客户端连接
- `disconnect` - 客户端断开
- `data_update` - 数据更新推送
- `request_update` - 请求立即更新
- `start_monitoring` - 开始后台监控
- `stop_monitoring` - 停止后台监控

### 管理操作接口

> ⚠️ 注意：所有管理操作通过会话验证身份，无需额外密码输入

- `POST /api/job/<id>/cancel` - 取消作业（管理员可取消任意作业，普通用户只能取消自己的作业）
- `POST /api/job/<id>/hold` - 挂起作业
- `POST /api/job/<id>/release` - 释放作业
- `POST /api/jobs/batch` - 批量操作（cancel/hold/release/suspend/resume）
- `POST /api/node/<name>/drain` - 排空节点（仅管理员）
- `POST /api/node/<name>/resume` - 恢复节点（仅管理员）
- `POST /api/verify-password` - 验证管理员密码

### 公告管理接口

- `GET /api/announcements` - 获取公告列表
- `POST /api/announcements` - 添加公告（仅管理员）
- `PUT /api/announcements/<id>` - 更新公告（仅管理员）
- `DELETE /api/announcements/<id>` - 删除公告（仅管理员）

### 预留管理接口

- `GET /api/reservations` - 获取所有预留
- `POST /api/reservations` - 创建预留
- `DELETE /api/reservations/<name>` - 删除预留

### WebShell 接口

- `GET /webshell` - WebShell 页面（登录或终端）
- `POST /webshell/login` - 系统用户登录
- `POST /webshell/logout` - 退出登录

#### WebShell Socket.IO 事件

- `shell_connect` - 连接 Shell 会话
- `shell_input` - 发送输入到 Shell
- `shell_output` - 接收 Shell 输出
- `shell_resize` - 调整终端大小
- `shell_disconnect` - 断开 Shell 会话
- `shell_ready` - Shell 就绪通知
- `shell_error` - Shell 错误通知

---

## 技术栈

- 后端：Python Flask + Flask-SocketIO
- 前端：原生 HTML5/CSS3/JavaScript
- 实时通信：**Socket.IO** (WebSocket/长轮询)
- 图表：CSS 饼图（无需外部依赖）

---

## 系统要求

- Python 3.7+
- Flask + Flask-SocketIO
- Slurm Workload Manager
- NVIDIA GPU 驱动（可选，用于 GPU 监控）

### GPU 监控说明

系统支持两种GPU信息获取方式：

1. **本地获取**：如果管理节点安装了 NVIDIA 驱动，直接本地执行 `nvidia-smi` 获取GPU信息

2. **远程获取（集群环境）**：如果管理节点没有GPU，系统会自动：
   - 通过 `sinfo` 查询具有GPU资源的计算节点
   - 通过SSH连接到这些节点执行 `nvidia-smi` 
   - 要求：管理节点到计算节点需配置**免密钥SSH登录**

配置免密钥SSH登录：
```bash
# 在管理节点上执行
ssh-keygen -t rsa  # 如果还没有密钥
ssh-copy-id user@compute-node01
ssh-copy-id user@compute-node02
# ... 对所有GPU节点执行
```

### WebShell 额外依赖

```bash
pip3 install python-pam pexpect
```

---

## 目录结构

```
slurm-web/
├── app.py                      # Flask + SocketIO 后端
├── start.sh                   # 启动脚本
├── install.sh                 # 安装脚本
├── test_jobs.sh               # 测试作业脚本
├── slurm-monitor.service      # Systemd 服务文件
├── config.json                # 配置文件（管理员密码等）
├── users.json                 # 用户数据库
├── README.md                  # 说明文档
├── README_DETAILED.md         # 详细功能文档
├── templates/
│   ├── base.html              # 基础模板
│   ├── index.html             # 主页面
│   ├── login.html             # 登录页面
│   ├── webshell.html          # WebShell 登录页
│   ├── webshell_terminal.html # WebShell 终端页
│   ├── qos.html               # QOS 管理
│   ├── accounts.html          # 账户管理
│   ├── resource_quotas.html   # 资源配额
│   └── disk_quota.html        # 磁盘配额
└── static/
    ├── css/
    │   ├── style.css          # 主样式
    │   └── webshell.css       # WebShell 样式
    └── js/
        ├── app.js             # 主脚本
        ├── webshell.js        # WebShell 登录脚本
        └── webshell_terminal.js # WebShell 终端脚本
```

---

## 更新日志

### v1.5.0 (2026-03-13)
- **新增登录系统** - 管理员和普通用户区分登录
  - 管理员登录：验证管理员密码，拥有全部功能
  - 普通用户登录：验证 Slurm 用户列表，默认密码 123456
  - 首次登录必须修改密码
- **新增磁盘配额监控** - 使用 `repquota -avus` 获取用户磁盘配额
- **新增信息公告模块** - 独立的公告管理页面
  - 管理员可添加、编辑、删除公告
  - 普通用户只能查看公告
  - 支持紧急/普通优先级
- **新增组织拓扑功能** - QOS/账户/用户关系可视化
  - 独立的"组织拓扑"页面（侧边栏导航）
  - 以思维导图方式展示 QOS → 账户 → 用户 的层级关系
  - 使用 SVG 曲线连接展示关联关系
  - 鼠标悬停显示资源配额限制信息
  - 数据从 `sacctmgr list associations tree` 命令获取，保证准确性
- **权限控制**：
  - 管理员：可执行所有管理操作（取消、暂停、恢复作业、Drain/Resume节点、创建预留等）
  - 普通用户：只能查看和提交作业，只能操作自己的作业
- **移除密码验证弹窗** - 所有操作通过会话验证身份，无需额外密码输入
- **侧边栏用户信息** - 显示当前用户名、用户类型和退出按钮
- **动态配置路径** - 不再硬编码路径，支持项目安装到任意目录

### v1.4.0 (2026-03-05)
- **新增作业详情抽屉** - 点击作业ID查看详细信息（资源、时间、工作目录等）
- **新增节点详情抽屉** - 点击节点名查看详细信息（配置、资源、Slurm设置等）
- **修复页面导航问题** - 修复资源配额/QOS/账户管理页面与主页面间的切换
- **修复节点管理功能** - 修复 Drain/Resume 节点操作的节点名传递问题
- **完善作业信息** - 添加提交时间字段到作业数据
- **新增优先级API** - 添加 `/api/priority` 接口获取详细优先级信息
- **添加调度原理文档** - 解释 AGE 和 Fairshare 的计算原理

### v1.3.0 (2026-03-02)
- **新增 Web Shell 功能** - 通过浏览器访问系统终端
- 系统 PAM 认证登录
- XTerm.js 终端仿真
- WebSocket 实时通信
- 支持常用终端快捷键

### v1.2.0 (2026-03-01)
- **新增用户资源使用详情** - 显示每个用户的 CPU/GPU 核时及占比
- **新增历史作业分页加载** - 默认 30 条，支持"显示全部"
- **新增管理员密码验证** - 保护敏感操作
- 优化优先级数据来源（使用 %Q 格式）
- 移除集群使用率趋势功能
- 移除 Fairshare 信息功能

### v1.1.0
- **新增 Socket.IO 实时通信**
- 双向实时数据推送
- 自动重连机制
- 连接状态显示（实时/轮询）

### v1.0.0
- 初始版本发布
- 完整的仪表盘功能
- 节点、作业、GPU 监控
- 用户统计和分区信息
- Server-Sent Events 实时更新

---

## 许可证

MIT License
