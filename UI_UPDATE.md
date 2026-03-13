# Slurm Web UI 更新说明

## 更新概述

本次更新将 `slurm-web` 项目的 UI 风格与 `slurm-bill-web` 统一，采用现代化的 Tailwind CSS 设计风格，同时添加了多个业内常用的功能。

## UI 风格变化

### 1. 整体设计
- **颜色主题**: 从深色主题改为浅色主题（bg-slate-50）
- **CSS 框架**: 引入 Tailwind CSS (通过 CDN)
- **字体**: 使用 Inter 字体（Google Fonts）
- **图标**: Font Awesome 6.4.0

### 2. 布局组件
- **侧边栏导航**: 统一的左侧导航栏设计
- **顶部栏**: 玻璃态效果 (glass) 的粘性顶部栏
- **卡片设计**: 圆角卡片 + 阴影 + 悬停效果 (card-hover)
- **表格样式**: 现代化表格设计 (table-modern)

### 3. 视觉元素
- **状态徽章**: 统一的颜色编码（成功=绿色，警告=黄色，危险=红色，信息=蓝色）
- **进度条**: 带动画效果的进度条
- **加载动画**: 旋转的 spinner
- **模态框**: 统一的模态框设计

## 新增功能

### 1. 作业提交功能
- **在线提交**: 通过 Web 界面直接提交 sbatch 作业
- **参数配置**: 支持设置分区、CPU、内存、GPU、运行时间等
- **脚本编辑**: 支持在线编辑作业脚本

API 端点:
```
POST /api/jobs/submit
```

### 2. 批量作业操作
- **批量取消**: 选择多个作业后批量取消
- **批量挂起/释放**: 批量控制作业状态

API 端点:
```
POST /api/jobs/batch
```

### 3. 改进的实时监控
- **Socket.IO 实时更新**: 使用 WebSocket 实现数据实时推送
- **自动刷新**: 支持定时自动刷新数据
- **连接状态指示**: 显示 WebSocket 连接状态

### 4. GPU 详细信息展示
- **温度监控**: 实时显示 GPU 温度（带颜色警告）
- **利用率图表**: 可视化 GPU 利用率
- **显存使用**: 进度条显示显存使用情况
- **功耗显示**: 显示 GPU 功耗信息

### 5. 数据可视化
- **Chart.js 图表**: 替换原有的 CSS 图表
- **节点状态饼图**: 显示节点分布
- **作业状态饼图**: 显示作业状态分布
- **CPU 资源饼图**: 显示 CPU 使用分布

### 6. 密码验证模态框
- **统一验证**: 所有管理操作使用统一的密码验证
- **安全增强**: 敏感操作需要管理员密码确认

## 文件变更

### 更新的模板文件
- `templates/base.html` - 新增基础模板（564行）
- `templates/index.html` - 完全重写（646行）
- `templates/accounts.html` - 完全重写（585行）
- `templates/resource_quotas.html` - 完全重写（544行）
- `templates/qos.html` - 完全重写（446行）
- `templates/webshell.html` - 完全重写（106行）
- `templates/webshell_terminal.html` - 完全重写（208行）

### 更新的后端代码
- `app.py` - 添加作业提交 API 和批量操作 API

## API 新增端点

```python
# 作业提交
POST /api/jobs/submit
Request: {
    "name": "作业名称",
    "partition": "分区名",
    "cpus": "CPU核心数",
    "memory": "内存(GB)",
    "gpus": "GPU数量",
    "nodes": "节点数",
    "time": "运行时间(HH:MM:SS)",
    "command": "执行命令"
}

# 批量作业操作
POST /api/jobs/batch
Request: {
    "job_ids": ["123", "124"],
    "action": "cancel|hold|release",
    "password": "管理员密码"
}
```

## 兼容性说明

- **功能兼容性**: 所有原有功能保持不变
- **API 兼容性**: 所有原有 API 端点正常工作
- **配置兼容性**: 配置文件格式不变
- **依赖兼容性**: 新增依赖通过 CDN 引入，无需额外安装

## 使用方法

1. 启动服务:
```bash
cd /root/slurm-web
python3 app.py
```

2. 访问 Web 界面:
```
http://localhost:5000
```

3. 新的功能入口:
- **作业提交**: 首页右下角的悬浮 "+" 按钮
- **批量操作**: 在作业列表页面选择多个作业
- **自动刷新**: 点击首页右下角的刷新按钮

## 技术栈

- **前端**: HTML5 + Tailwind CSS + Chart.js + Font Awesome
- **后端**: Flask + Flask-SocketIO
- **实时通信**: Socket.IO (WebSocket)
- **字体**: Inter (Google Fonts)

## 注意事项

1. 确保网络可以访问 CDN 资源（Tailwind CSS、Chart.js、Font Awesome）
2. 如需离线使用，可以下载相关 CDN 资源到本地
3. Web Shell 功能需要安装 `python-pam` 和 `pexpect`
4. 所有管理操作默认需要管理员密码验证
