import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

config_name = 'development'
if len(sys.argv) > 1:
    config_name = sys.argv[1]

app = create_app(config_name)

if __name__ == '__main__':
    print(f'Starting OJ System on http://localhost:5000 (config: {config_name})')
    print(f'Judge engine status: {"running" if app.judge_engine.is_running else "stopped"}')
    app.run(debug=app.config.get('DEBUG', False), port=5000)
