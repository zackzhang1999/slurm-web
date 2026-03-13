# 用户统计功能修复说明

## 问题
用户统计页面中的"用户作业分布"和"用户CPU使用"图表没有数据显示。

## 原因
1. 原代码没有正确初始化 Chart.js 图表
2. 没有从后端 API 获取历史统计数据
3. 只使用了实时数据（squeue），无法展示历史趋势

## 修复内容

### 1. 新增时间范围选择器
- 支持选择不同时间范围：今天、过去7天、过去30天、过去90天
- 根据选择的时间范围动态加载数据

### 2. 新增图表初始化
- 使用 Chart.js 正确初始化用户作业分布柱状图
- 使用 Chart.js 正确初始化用户CPU使用柱状图
- 显示 Top 10 用户的数据

### 3. 新增数据加载函数
```javascript
loadUsersDataWithHistory(days)     // 加载历史统计数据
loadUsersTableFromHistory(users)   // 从历史数据渲染表格
updateUserCharts(users)            // 更新图表
updateUserChartsFromRealtime(stats) // 从实时数据更新图表（备用）
```

### 4. 数据来源
- 使用 `/api/stats/users/top` API 获取历史统计数据
- 使用 `sreport user topuser` 命令获取数据
- 如果 Accounting 未启用，回退到 `squeue` 实时数据

## 图表说明

### 用户作业分布 (Top 10)
- 类型：柱状图
- 数据：作业数量
- 排序：按作业数从高到低
- 显示：前10名用户

### 用户CPU使用 (Top 10)
- 类型：柱状图
- 数据：CPU使用时间（小时）
- 排序：按CPU时间从高到低
- 显示：前10名用户

## 使用方式

1. 点击侧边栏"用户统计"
2. 选择时间范围（默认过去7天）
3. 查看图表和表格数据
4. 点击刷新按钮更新数据

## API 端点

```
GET /api/stats/users/top?days={days}&top={top}

参数:
  - days: 统计天数 (1, 7, 30, 90)
  - top: 返回用户数 (默认10)

返回:
  [
    {
      "login": "用户名",
      "jobs": "作业数",
      "cpu_time": "CPU时间(小时)",
      "usage": "使用量",
      "energy": "能耗"
    }
  ]
```

## 注意事项

1. **Accounting 数据**: 历史统计需要 Slurm Accounting 数据库支持。如果未启用，会显示实时数据。
2. **时间范围**: 大时间范围（如90天）的数据加载可能需要较长时间。
3. **数据准确性**: 统计数据基于 sacct/sreport，只包含已完成的作业。

## 文件变更

- `templates/index.html` - 修改用户统计页面，添加图表初始化和数据加载逻辑
