import sys
import os
import multiprocessing

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

config_name = 'development'
if len(sys.argv) > 1:
    config_name = sys.argv[1]

# Keep import-time app creation side-effect free for multiprocessing spawn.
app = create_app(config_name, start_judge_engine=False)

if __name__ == '__main__':
    multiprocessing.freeze_support()
    app = create_app(config_name, start_judge_engine=True)
    threaded = os.environ.get('FLASK_THREADED', '1') != '0'
    use_reloader = os.environ.get('FLASK_RELOADER', '0') == '1'
    print(f'Starting OJ System on http://localhost:5000 (config: {config_name})')
    print(f'Judge engine status: {"running" if app.judge_engine.is_running else "stopped"}')
    print(f'Flask threaded mode: {"on" if threaded else "off"}')
    print(f'Flask reloader: {"on" if use_reloader else "off"}')
    app.run(
        debug=app.config.get('DEBUG', False),
        port=5000,
        threaded=threaded,
        use_reloader=use_reloader,
    )
