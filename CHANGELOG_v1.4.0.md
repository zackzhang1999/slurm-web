# Slurm 集群监控系统 v1.4.0 更新日志

**发布日期**: 2026-03-05

---

## 🆕 最新更新 (2026-03-20)

### 1. 作业详情抽屉增强 ⭐ 重要改进
参考 `jobinfo` 脚本，大幅增强作业详情抽屉的信息展示：

**新增信息字段：**
- **账户信息**: Account, QOS
- **完整时间线**: Submit, Start, End, Waited, Reserved walltime, Used walltime
- **CPU 使用详情**: Used CPU time, % User (Computation), % System (I/O)
- **实际资源使用**: Max Mem used, Max Disk Write, Max Disk Read
- **提交命令**: SubmitLine (如 Slurm 版本支持)
- **退出码**: 显示作业完成状态

**技术实现：**
- 后端使用 `sacct` 获取历史/已完成作业的详细信息
- 使用 `sstat` 获取运行中作业的实时统计
- 使用 `squeue` 获取待运行作业的等待原因
- 智能显示：仅当有数据时才显示对应信息区域

### 2. 历史任务功能 ⭐ 新增
新增历史任务查看功能，展示过去 30 天内的所有作业：

**功能特点：**
- 标签页切换：活跃作业 / 历史任务
- 分页展示：默认每页 50 条，支持 50/100 条每页
- 表格字段：作业ID、名称、用户、账户、分区、状态、退出码、节点、CPU、GPU、**预留内存、最大内存、磁盘写入、磁盘读取**、运行时间、提交时间
- 筛选功能：按状态（已完成/失败/已取消/超时）、分区筛选
- 搜索功能：按用户名搜索
- 详情抽屉：点击作业ID查看完整信息（与活跃作业共用详情抽屉）

**API 接口：**
- `GET /api/jobs/history?days=30&page=1&per_page=50&state=&user=&partition=`
- 支持分页、筛选、排序（按提交时间倒序）

### 3. 作业暂停/恢复功能
- 支持暂停正在运行的作业 (`scontrol suspend`)
- 支持恢复已暂停的作业 (`scontrol resume`)
- 前端界面：每个运行中作业显示暂停按钮，已暂停作业显示恢复按钮
- 批量操作：支持暂停/恢复多个作业
- 位置：作业管理页面

### 4. 资源预留管理
- 将预留管理功能集成到节点监控页面
- 支持创建、删除资源预留
- API: `/api/reservations` (GET/POST/DELETE)
- 位置：节点监控页面下方

### 5. 功能模块调整
- 移除独立的预留管理、许可证、电源管理、网络拓扑菜单项
- 预留管理功能已集成到节点监控页面

---

## 🎯 主要更新

### 1. 新增抽屉式详情面板

#### 作业详情抽屉
- 点击任意作业ID打开详情抽屉
- 显示内容:
  - 基本信息: 作业ID、状态、用户、分区、优先级
  - 资源分配: 节点数、CPU、内存、GPU、分配节点
  - 时间信息: 提交时间、开始时间、运行时间、剩余时间
  - 工作目录: 完整路径
  - 操作按钮: 取消作业、查看输出
- 支持 ESC 键关闭，点击遮罩层关闭

#### 节点详情抽屉
- 点击任意节点名打开详情抽屉
- 显示内容:
  - 基本信息: 节点名、状态、分区、架构
  - 资源配置: CPU核心、负载、内存、GPU
  - Slurm配置: 权重、版本、特征
  - 操作按钮: Drain节点、恢复节点（智能显示）
- 支持 ESC 键关闭

### 2. 页面导航修复
- 修复资源配额/QOS管理/账户管理页面与主页面间的切换问题
- 独立页面点击SPA导航链接时正确跳转回主页

### 3. 节点管理功能修复
- 修复 Drain/Resume 节点操作的节点名传递问题
- 添加 URL 编码处理特殊字符
- 操作前验证节点存在性
- 添加详细调试日志

### 4. 作业数据完善
- 添加提交时间字段 (`submit_time`) 到 squeue 输出
- 格式: `%V` (SubmitTime)

### 5. 新增优先级API
- 接口: `GET /api/priority`
- 数据来源: `sprio` 命令
- 返回字段: job_id, priority, age_raw, age, fairshare, jobsize, partition, qos, qos_name, tres

---

## 📚 文档更新

### 新增内容
1. **USER_GUIDE.md** - 添加作业/节点详情抽屉使用说明
2. **USER_GUIDE.md** - 添加 AGE 和 Fairshare 计算原理详解
3. **API文档** - 添加 `/api/priority` 接口文档
4. **README.md** - 更新功能列表和更新日志

### AGE 为 0 的解释
```
AGE = 等待时间 / PriorityMaxAge

例如:
- 作业提交 10 分钟 = 600 秒
- PriorityMaxAge = 14 天 = 1,209,600 秒
- AGE = 600 / 1,209,600 ≈ 0.000496 (显示为 0)
```

结论: AGE 为 0 是正常现象，不影响作业调度。

### Fairshare 计算原理
```
Fairshare = 2^(-U/S)

U = 加权历史使用量
S = 应得份额

值含义:
- 100: 完全未使用，最高优先级
- 67: 使用略低于平均，中高优先级
- 50: 使用等于应得份额
- 25: 使用远超应得份额
```

---

## 🔧 技术细节

### 前端修改
- `base.html`: 
  - 添加作业/节点详情抽屉 HTML 和 JavaScript
  - 增强 `loadJobDetailData()` 函数，支持从历史任务数据查找
  - 增强 `renderJobDetail()` 函数，适配多种数据格式（squeue/scontrol/sacct）
  - 添加 CPU/内存/磁盘 I/O 详情区域的智能显示逻辑
- `index.html`: 
  - 作业/节点表格添加点击事件
  - 添加历史任务标签页和表格
  - 实现历史任务分页、筛选、搜索功能
  - 将 `historyJobsPagination` 挂载到 `window` 对象供详情抽屉访问
- 添加 `window.allData` 全局暴露

### 后端修改
- `app.py`: 
  - **增强 `/api/job/<id>` 接口**: 使用 `sacct` + `sstat` + `squeue` 获取详细作业信息
    - `sacct`: 获取历史/已完成作业的详细信息（CPU时间、内存使用、磁盘I/O等）
    - `sstat`: 获取运行中作业的实时统计
    - `squeue`: 获取待运行作业的等待原因
    - 添加 `format_bytes()` 辅助函数
  - **新增 `/api/jobs/history` 接口**: 获取历史任务列表（过去30天）
    - 支持分页、筛选、排序
    - 智能合并主作业和 `.batch` 步骤的数据
    - 字段: JobID, JobName, User, Account, Partition, State, ExitCode, Submit, Start, End, Elapsed, Timelimit, ReqCPUS, ReqMem, ReqTRES, MaxRSS, MaxDiskWrite, MaxDiskRead, TotalCPU, NNodes
  - 添加 `/api/priority` 接口
  - 修复 Drain/Resume API 的节点名处理
  - 添加 URL 解码和引号处理
  - 修复 f-string 语法错误

### 数据格式适配
- 兼容 `squeue`、`scontrol`、`sacct` 三种字段命名:
  - squeue: `job_id`, `user`, `name`, `state`, `submit_time`
  - scontrol: `jobid`, `userid`, `jobname`, `jobstate`
  - sacct: `jobid`, `userid`, `jobname`, `state`, `submittime`, `maxrss`, `maxdiskwrite`, `maxdiskread`

### 历史任务数据合并策略
```
1. 使用 sacct 获取所有步骤（移除 -X 参数）
2. 主作业（如 77）包含: 基本信息、资源请求、时间信息
3. .batch 步骤（如 77.batch）包含: 实际资源使用（MaxRSS, MaxDiskWrite, MaxDiskRead, TotalCPU）
4. 使用字典合并同一作业的不同步骤数据
5. 最终结果包含完整的基本信息和资源使用数据
```

---

## 🐛 修复的 Bug

1. **页面切换失效** - 独立页面无法切换到主页面
2. **Drain节点失败** - "Invalid node name specified" 错误
3. **f-string语法错误** - Python 3.11+ 的嵌套表达式问题
4. **变量生命周期问题** - `closeNodeDetail()` 后 `currentDetailNodeName` 被清空

---

## 📝 配置文件

无需修改配置文件，所有更新向后兼容。

---

## 🔗 相关文档

- [USER_GUIDE.md](USER_GUIDE.md) - 完整使用指南
- [README.md](README.md) - 项目说明
- [README_DETAILED.md](README_DETAILED.md) - 功能详细介绍
