# Slurm 集群监控系统 v1.4.0 更新日志

**发布日期**: 2026-03-05

---

## 🆕 最新更新 (2026-03-10)

### 1. 作业暂停/恢复功能
- 支持暂停正在运行的作业 (`scontrol suspend`)
- 支持恢复已暂停的作业 (`scontrol resume`)
- 前端界面：每个运行中作业显示暂停按钮，已暂停作业显示恢复按钮
- 批量操作：支持暂停/恢复多个作业
- 位置：作业管理页面

### 2. 资源预留管理
- 将预留管理功能集成到节点监控页面
- 支持创建、删除资源预留
- API: `/api/reservations` (GET/POST/DELETE)
- 位置：节点监控页面下方

### 3. 功能模块调整
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
- `base.html`: 添加作业/节点详情抽屉 HTML 和 JavaScript
- `index.html`: 作业/节点表格添加点击事件
- 添加 `window.allData` 全局暴露

### 后端修改
- `app.py`: 
  - 添加 `/api/priority` 接口
  - 修复 Drain/Resume API 的节点名处理
  - 添加 URL 解码和引号处理
  - 修复 f-string 语法错误

### 数据格式适配
- 兼容 `squeue` 和 `scontrol` 两种字段命名
- squeue: `job_id`, `user`, `name`, `state`
- scontrol: `jobid`, `userid`, `jobname`, `jobstate`

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
