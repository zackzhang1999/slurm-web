import sys
sys.path.insert(0, '/root/slurm-web')

# Import all from app
from app import *

if __name__ == '__main__':
    print("Starting server...")
    print("Routes:", [r.rule for r in app.url_map.iter_rules() if 'log' in r.rule])
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
