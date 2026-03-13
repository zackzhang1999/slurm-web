# CPU/GPU 时间统计统一化修复

## 问题
1. 用户统计页面的图表数据不对
2. 用户的 CPU 用时和统计报表内的 CPU 使用时间对不上
3. 需要统一所有地方的 CPU 和 GPU 时间统计方法

## 解决方案

### 1. 统一统计函数
使用 `get_user_resource_usage(hours)` 作为唯一的用户资源使用统计函数：
- 使用 `sacct` 命令获取数据
- 统一计算 CPU 时间（分钟）
- 统一计算 GPU 时间（分钟 = 运行时间 × GPU 数量）
- 返回每个用户的占比

### 2. 修改的 API

#### `/api/stats/users/top`
- 现在使用 `get_user_resource_usage()` 获取数据
- 返回格式兼容原有代码
- 包含字段：`login`, `jobs`, `cpu_time`, `cpu_minutes`, `gpu_minutes`, `cpu_percent`, `gpu_percent`

#### `/api/stats/users/detailed` (新增)
- 返回详细的 CPU/GPU 资源使用数据
- 包含总时间（所有用户合计）
- 适合用户统计页面使用

#### `/api/stats/jobs`
- 现在使用 `get_user_resource_usage()` 获取 CPU 时间
- 确保与用户信息一致
- 新增 `total_gpu_hours` 字段

### 3. 用户统计页面更新

#### 图表展示
**用户 CPU 时间分布 (Top 10)**
- 柱状图展示 CPU 使用时间最多的前10名用户
- 显示 CPU 时间（小时）
- 显示占总时间的百分比

**用户 GPU 时间分布 (Top 10)**
- 柱状图展示 GPU 使用时间最多的前10名用户
- 显示 GPU 时间（小时）
- 显示占总时间的百分比
- 无 GPU 使用时显示提示

#### 表格展示
- 排名（前三名金色/银色/铜色）
- 用户名
- 作业数
- CPU时间(小时) + 占比进度条
- GPU时间(小时) + 占比进度条

#### 总时间显示
- 页面顶部显示总 CPU 时间和总 GPU 时间

### 4. 数据单位统一

| 指标 | 存储单位 | 显示单位 | 说明 |
|------|----------|----------|------|
| CPU 时间 | 分钟 | 小时 | 除以 60 |
| GPU 时间 | 分钟 | 小时 | 除以 60 |
| 占比 | 百分比 | 百分比 | 保留1位小数 |

### 5. 计算公式

```python
# CPU 时间
cpu_seconds = parse_time_to_seconds(cpu_time_from_sacct)
cpu_minutes = cpu_seconds / 60.0

# GPU 时间
gpu_count = extract_gpu_count_from_alloc_tres
elapsed_seconds = parse_time_to_seconds(elapsed_time)
elapsed_minutes = elapsed_seconds / 60.0
gpu_minutes = elapsed_minutes * gpu_count

# 占比
cpu_percent = (user_cpu_minutes / total_cpu_minutes) * 100
gpu_percent = (user_gpu_minutes / total_gpu_minutes) * 100
```

## 验证方法

1. 访问用户统计页面
2. 检查 CPU 时间和 GPU 时间是否合理
3. 对比统计报表页面的总 CPU 时间
4. 检查所有百分比加起来是否约等于 100%

## 文件变更

- `app.py`: 统一 API 使用 `get_user_resource_usage()`
- `templates/index.html`: 更新用户统计页面图表和表格

## 注意事项

1. 所有 CPU/GPU 时间现在使用统一的计算方式
2. 统计报表和用户统计的数据现在是一致的
3. GPU 时间只统计 AllocTRES 中包含 GPU 的作业
4. 如果 Accounting 未启用，会显示实时数据（可能不准确）
