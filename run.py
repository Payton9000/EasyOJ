import multiprocessing
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

# FLASK_ENV was documented in .env.example but never read, so an operator who set
# it to "production" silently got the development profile with DEBUG on.
config_name = os.environ.get('FLASK_ENV', 'development')
if len(sys.argv) > 1:
    config_name = sys.argv[1]

# Keep import-time app creation side-effect free for multiprocessing spawn.
app = create_app(config_name, start_judge_engine=False)

if __name__ == '__main__':
    multiprocessing.freeze_support()
    app = create_app(config_name, start_judge_engine=True)
    threaded = os.environ.get('FLASK_THREADED', '1') != '0'
    use_reloader = os.environ.get('FLASK_RELOADER', '0') == '1'
    default_host = '0.0.0.0' if config_name == 'production' else '127.0.0.1'
    host = os.environ.get('EASYOJ_HOST', default_host)
    debug_mode = app.config.get('DEBUG', False)
    if debug_mode and host not in ('127.0.0.1', 'localhost', '::1'):
        print(
            'Refusing to start in DEBUG mode on non-loopback address '
            f'({host}). Werkzeug debugger would allow remote code execution.',
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        port = max(1, min(65535, int(os.environ.get('EASYOJ_PORT', '5000'))))
    except ValueError:
        port = 5000
    print(f'Starting OJ System on http://{host}:{port} (config: {config_name})')
    print(f'Judge engine status: {"running" if app.judge_engine.is_running else "stopped"}')
    print(f'Flask threaded mode: {"on" if threaded else "off"}')
    print(f'Flask reloader: {"on" if use_reloader else "off"}')
    if config_name == 'production':
        from waitress import serve

        web_threads = max(2, min(16, os.cpu_count() or 2))
        print(f'Waitress threads: {web_threads}')
        serve(app, host=host, port=port, threads=web_threads, connection_limit=256)
    else:
        app.run(
            debug=app.config.get('DEBUG', False),
            host=host,
            port=port,
            threaded=threaded,
            use_reloader=use_reloader,
        )
