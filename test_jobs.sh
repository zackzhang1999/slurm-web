#!/bin/bash
# 创建测试作业用于演示监控页面

echo "提交测试作业到 Slurm..."

# CPU 测试作业
cat > /tmp/cpu_job.sh << 'EOF'
#!/bin/bash
#SBATCH --job-name=cpu_test
#SBATCH --output=/tmp/cpu_test_%j.out
#SBATCH --time=00:10:00
#SBATCH --partition=debug
#SBATCH --cpus-per-task=4

echo "CPU Test Job Started at: $(date)"
echo "Job ID: $SLURM_JOB_ID"
echo "Allocated CPUs: $SLURM_CPUS_PER_TASK"
echo "Node: $SLURM_NODELIST"

# 模拟计算任务
for i in {1..30}; do
    echo "Computing step $i/30..."
    sleep 2
done

echo "Job Finished at: $(date)"
EOF

# 内存测试作业
cat > /tmp/mem_job.sh << 'EOF'
#!/bin/bash
#SBATCH --job-name=mem_test
#SBATCH --output=/tmp/mem_test_%j.out
#SBATCH --time=00:10:00
#SBATCH --partition=debug
#SBATCH --mem=1024

echo "Memory Test Job Started at: $(date)"
echo "Allocated Memory: 1024 MB"

# 分配内存并等待
python3 -c "
import time
data = 'x' * (512 * 1024 * 1024)  # 512MB
print('Allocated 512MB memory')
time.sleep(60)
"
EOF

chmod +x /tmp/cpu_job.sh /tmp/mem_job.sh

# 提交作业
echo "提交 CPU 测试作业..."
sbatch /tmp/cpu_job.sh

echo "提交内存测试作业..."
sbatch /tmp/mem_job.sh

echo ""
echo "查看作业队列:"
squeue

echo ""
echo "监控页面将显示这些作业的状态变化"
echo "访问 http://localhost:5000 查看监控"
