import atexit
import os

from flask import Flask
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask_login import LoginManager
from flask_login import current_user
from flask_login import logout_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFError
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event

from app.i18n import translate as t

try:
    from flask_migrate import Migrate
except Exception:
    Migrate = None

from app.config import config
from app.utils.retention import cleanup_expired_directories
from app.utils.retention import cleanup_expired_files
from app.utils.startup_maintenance import run_sqlite_migrations

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate() if Migrate is not None else None


def create_app(config_name='default', start_judge_engine=True, config_overrides=None):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    if config_overrides:
        app.config.update(config_overrides)

    config_cls = config[config_name]
    if hasattr(config_cls, 'init_app'):
        config_cls.init_app(app)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    from app.i18n import init_i18n

    init_i18n(app)
    if migrate is not None:
        migrate.init_app(app, db)

    login_manager.login_view = 'web.login'
    login_manager.login_message_category = 'error'
    login_manager.session_protection = 'strong'

    from app.utils.time_utils import format_local_datetime
    from app.utils.time_utils import format_local_datetime_input

    @app.template_filter('local_datetime')
    def local_datetime_filter(value, fmt='%Y-%m-%d %H:%M'):
        return format_local_datetime(
            value,
            fmt,
            local_timezone=app.config.get('LOCAL_TIMEZONE'),
        )

    @app.template_filter('local_datetime_input')
    def local_datetime_input_filter(value):
        return format_local_datetime_input(
            value,
            local_timezone=app.config.get('LOCAL_TIMEZONE'),
        )

    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User

        return db.session.get(User, int(user_id))

    @app.before_request
    def revoke_inactive_sessions():
        if request.endpoint == 'static':
            return None
        if current_user.is_authenticated and not current_user.is_active:
            logout_user()
            if request.path.startswith('/api') or request.path.startswith('/judge'):
                return jsonify({'code': 401, 'message': 'Account is disabled'}), 401
            return redirect(url_for('web.login'))
        if (
            current_user.is_authenticated
            and current_user.must_change_password
            and request.endpoint not in {'static', 'web.change_password', 'web.logout'}
        ):
            if request.path.startswith('/api') or request.path.startswith('/judge'):
                return jsonify({'code': 403, 'message': 'Password change required'}), 403
            return redirect(url_for('web.change_password'))
        return None

    # Register blueprints
    from app.web import admin_bp
    from app.web import web_bp
    from app.web.health import health_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(health_bp)

    from app.api import api_bp

    app.register_blueprint(api_bp, url_prefix='/api')

    from app.judge import judge_bp

    app.register_blueprint(judge_bp, url_prefix='/judge')

    _register_json_error_handlers(app)

    with app.app_context():
        _configure_sqlite_pragmas(app)
        db.create_all()
        _run_schema_migrations(app)
        cleanup_expired_files(
            app.config.get('JUDGE_LOG_DIR', ''),
            max_age_seconds=app.config.get('JUDGE_LOG_RETENTION_SECONDS', 14 * 24 * 3600),
            max_files=app.config.get('JUDGE_LOG_CLEANUP_MAX_FILES', 100),
        )
        base_dir = app.config.get('BASE_DIR')
        if base_dir:
            cleanup_expired_directories(
                os.path.join(base_dir, 'data', 'temp'),
                max_age_seconds=app.config.get('JUDGE_TEMP_RETENTION_SECONDS', 2 * 24 * 3600),
                max_dirs=app.config.get('JUDGE_TEMP_CLEANUP_MAX_DIRS', 20),
            )

    # Initialize and start judge engine
    from app.judge.engine import JudgeEngine

    judge_engine = JudgeEngine(app, config_name=config_name)
    app.judge_engine = judge_engine

    if start_judge_engine and not app.config.get('TESTING'):
        judge_engine.start()
        atexit.register(_shutdown_judge_engine, judge_engine)

    @app.teardown_appcontext
    def shutdown_judge_engine(exception=None):
        pass  # Engine lifecycle managed by atexit + daemon workers

    return app


def _shutdown_judge_engine(engine):
    try:
        engine.stop()
    except Exception:
        pass


def _register_json_error_handlers(app):
    def _json_error(code, message):
        return jsonify({'code': code, 'message': message}), code

    def _is_api_request():
        return request.path.startswith('/api') or request.path.startswith('/judge')

    def _render_error_page(code, message):
        try:
            return render_template('error.html', error_code=code, error_message=message), code
        except Exception:
            return f'<h1>{code}</h1><p>{message}</p>', code

    @app.errorhandler(403)
    def forbidden(e):
        if _is_api_request():
            return _json_error(403, 'Forbidden')
        return _render_error_page(403, t('error.forbidden'))

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        if _is_api_request():
            return _json_error(400, 'CSRF token missing or invalid')
        return _render_error_page(400, t('error.csrf'))

    @app.errorhandler(404)
    def not_found(e):
        if _is_api_request():
            return _json_error(404, 'Resource not found')
        return _render_error_page(404, t('error.not_found'))

    @app.errorhandler(405)
    def method_not_allowed(e):
        if _is_api_request():
            return _json_error(405, 'Method not allowed')
        return e

    @app.errorhandler(413)
    def too_large(e):
        if _is_api_request():
            return _json_error(413, 'Request payload too large')
        return _render_error_page(413, t('error.too_large'))

    @app.errorhandler(500)
    def server_error(e):
        if _is_api_request():
            return _json_error(500, 'Internal server error')
        return _render_error_page(500, t('error.server'))


def _configure_sqlite_pragmas(app):
    extension_key = 'easyoj_sqlite_pragmas_registered'
    if app.extensions.get(extension_key):
        return

    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite:///'):
        return

    busy_timeout_ms = max(5000, app.config.get('SQLITE_BUSY_TIMEOUT_MS', 30000))

    engine = db.engine

    @event.listens_for(engine, 'connect')
    def _set_sqlite_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute(f'PRAGMA busy_timeout={busy_timeout_ms}')
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.execute('PRAGMA synchronous=NORMAL')
        cursor.close()

    app.extensions[extension_key] = True


def _run_schema_migrations(app):
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite:///'):
        return

    db_path = db_uri.replace('sqlite:///', '', 1)
    if db_path == ':memory:':
        return

    def migrate_application(connection):
        columns = {
            'user': {
                'must_change_password': 'BOOLEAN DEFAULT 0',
                'failed_login_count': 'INTEGER DEFAULT 0',
                'locked_until': 'DATETIME',
                'last_login_at': 'DATETIME',
            },
            'judge_task': {
                'last_heartbeat_at': 'DATETIME',
                'retry_count': 'INTEGER DEFAULT 0',
                'last_error': 'TEXT',
                'debug_log_path': 'VARCHAR(255)',
            },
        }
        for table, additions in columns.items():
            existing = {
                row[1] for row in connection.execute(f"PRAGMA table_info('{table}')").fetchall()
            }
            for name, column_type in additions.items():
                if name not in existing:
                    connection.execute(f'ALTER TABLE {table} ADD COLUMN {name} {column_type}')

        connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_contest_problem_status '
            'ON submission (contest_id, problem_id, status)'
        )
        connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_contest_user_submitted_at '
            'ON submission (contest_id, user_id, submitted_at)'
        )

    def migrate_submission_idempotency(connection):
        existing = {
            row[1] for row in connection.execute("PRAGMA table_info('submission')").fetchall()
        }
        if 'client_token' not in existing:
            connection.execute('ALTER TABLE submission ADD COLUMN client_token VARCHAR(128)')
        connection.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_contest_submission_client_token '
            'ON submission (user_id, contest_id, problem_id, client_token)'
        )

    run_sqlite_migrations(
        db_path,
        [migrate_application, migrate_submission_idempotency],
        timeout_seconds=max(1, app.config.get('SQLITE_BUSY_TIMEOUT_MS', 30000) / 1000),
    )
