# Slurm 作业优先级 AGE 为 0 说明

## 原因分析

`sprio -l` 显示 AGE 为 0 是**正常现象**，原因如下：

### 1. 时间单位问题
- AGE 计算的是作业在队列中等待的时间
- 对于刚提交的作业（几分钟内），AGE 值极小
- sprio 显示时可能截断为 0

### 2. 系统配置检查
```bash
# 查看优先级配置
scontrol show config | grep Priority
```

当前系统配置：
- `PriorityType=priority/multifactor` ✅ 已启用多因子优先级
- `PriorityWeightAge=1000` ✅ AGE 权重为 1000
- `PriorityMaxAge=14-00:00:00` ✅ 最大年龄 14 天

### 3. AGE 计算方法
```
AGE = (当前时间 - 提交时间) / PriorityMaxAge
```

例如：
- 作业提交 10 分钟 = 600 秒
- PriorityMaxAge = 14 天 = 1,209,600 秒
- AGE = 600 / 1,209,600 ≈ 0.000496

### 4. 查看原始 AGE 值
```bash
# 显示更精确的 AGE 值
sprio -o "%i|%Q|%a" -t PENDING

# 输出格式：JOBID|PRIORITY|AGE(原始值)
# 例如：163|66|0.0000521
```

## 如何让 AGE 不为 0

1. **等待更长时间** - 作业在队列中等待几小时后 AGE 会增加
2. **缩短 PriorityMaxAge** - 减小分母，使 AGE 增长更快
   ```bash
   # 在 slurm.conf 中设置
   PriorityMaxAge=1-00:00:00  # 1天而不是14天
   ```
3. **增加 PriorityWeightAge** - 提高 AGE 在优先级中的权重

## 结论

AGE 为 0 不影响作业调度，只是表示作业刚刚提交。作业的优先级仍然由其他因子（如 FAIRSHARE）计算得出。
