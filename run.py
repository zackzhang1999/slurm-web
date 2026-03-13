#!/opt/anaconda3/bin/python3
import sys
sys.path.insert(0, '/root/slurm-web')

# Import all from app
exec(open('/root/slurm-web/app.py').read())
