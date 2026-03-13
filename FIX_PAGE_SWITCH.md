# 页面切换功能修复说明

## 问题
点击"节点监控"、"作业管理"等侧边栏导航链接时，页面没有切换到对应的内容，而是停留在仪表盘。

## 原因
原来的项目是一个单页应用（SPA），通过 JavaScript 切换显示不同的 `.page` 区块。在重写 UI 时，我没有实现这个功能。

## 修复内容

### 1. base.html 修改
- 添加 `window.switchPage(page)` 全局函数
- 侧边栏导航链接改为 `onclick="switchPage('xxx'); return false;"`
- 添加 `window.currentPage` 变量跟踪当前页面
- 支持浏览器前进/后退按钮（history API）
- 支持 URL 参数 `?page=xxx` 直接访问特定页面

### 2. index.html 修改
- 将原来的单页内容拆分为多个 `page-section` 区块：
  - `page-dashboard` - 仪表盘
  - `page-nodes` - 节点监控
  - `page-jobs` - 作业管理
  - `page-gpu` - GPU监控
  - `page-users` - 用户统计
  - `page-partitions` - 分区信息
  - `page-statistics` - 统计报表

- 每个页面都有完整的功能：
  - **节点监控**: 节点列表、状态筛选、搜索
  - **作业管理**: 作业列表、批量操作（取消/挂起/释放）、筛选
  - **GPU监控**: GPU卡片展示、进程列表
  - **用户统计**: 用户作业分布图、CPU使用图、用户详情表
  - **分区信息**: 分区卡片、作业统计表
  - **统计报表**: 时间范围选择、完成/失败统计、用户排行

### 3. 数据加载优化
- 使用 `window.onDataUpdate` 统一处理数据更新
- 根据当前页面动态加载对应数据
- 支持 Socket.IO 实时更新

## 使用方式

### 侧边栏导航
点击侧边栏的任意导航项，页面会无刷新切换到对应内容。

### URL 直接访问
- `http://localhost:5000/` - 仪表盘
- `http://localhost:5000/?page=nodes` - 节点监控
- `http://localhost:5000/?page=jobs` - 作业管理
- `http://localhost:5000/?page=gpu` - GPU监控
- `http://localhost:5000/?page=users` - 用户统计
- `http://localhost:5000/?page=partitions` - 分区信息
- `http://localhost:5000/?page=statistics` - 统计报表

### 浏览器前进/后退
支持浏览器的前进和后退按钮，可以正常切换页面。

## 文件变更
- `templates/base.html` - 添加页面切换逻辑
- `templates/index.html` - 添加各页面内容区块
