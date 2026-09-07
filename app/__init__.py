import atexit
import logging
import os
import threading
from datetime import datetime

from flask import Flask
from flask import flash
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

    @app.template_filter('file_size')
    def file_size_filter(num_bytes):
        """Human-readable byte count; raw numbers like 13417 mean little to a teacher."""
        try:
            value = float(num_bytes)
        except (TypeError, ValueError):
            return '-'
        if value < 1024:
            return f'{int(value)} B'
        if value < 1024 * 1024:
            return f'{value / 1024:.1f} KB'
        return f'{value / (1024 * 1024):.1f} MB'

    @app.template_filter('memory_size')
    def memory_size_filter(kilobytes):
        """Render a KiB reading consistently as MB.

        The same field was previously shown as truncated MB, raw KB, or two-decimal
        MB depending on the page, so 900 KiB appeared as "0 MB" in one place and
        "900KB" in another.
        """
        if kilobytes is None or kilobytes == '':
            return '-'
        try:
            value = float(kilobytes)
        except (TypeError, ValueError):
            return '-'
        if value <= 0:
            return '-'
        megabytes = value / 1024
        if megabytes < 0.1:
            return '< 0.1 MB'
        return f'{megabytes:.1f} MB'

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
            # Without this the student is bounced to the sign-in page mid-task with
            # no explanation, then told their password is wrong when they retry.
            flash(t('flash.account_disabled'), 'error')
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
        # Recorded so the administrator page can report uptime in words.
        app.config['SERVICE_STARTED_AT'] = datetime.utcnow()
        atexit.register(_shutdown_judge_engine, judge_engine)
        _start_backup_scheduler(app)

    return app


def _shutdown_judge_engine(engine):
    try:
        engine.stop()
    except Exception:
        logging.getLogger(__name__).exception('Judge engine shutdown failed')


def _start_backup_scheduler(app):
    """Back up on start, then once per interval, from one daemon thread.

    A classroom host is rebooted often and rarely runs an external scheduler, so
    the service takes responsibility for its own backups. ``min_interval_seconds``
    keeps frequent restarts from filling the directory with near-identical copies.
    """
    if not app.config.get('BACKUP_ENABLED', True):
        return
    from app.utils.backup import create_backup

    database_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    backup_dir = app.config.get('BACKUP_DIR')
    if not database_uri.startswith('sqlite:///') or not backup_dir:
        return

    keep = app.config.get('BACKUP_KEEP', 14)
    interval = max(600, int(app.config.get('BACKUP_INTERVAL_SECONDS', 24 * 3600)))
    min_interval = int(app.config.get('BACKUP_MIN_INTERVAL_SECONDS', interval * 5 // 6))
    logger = logging.getLogger(__name__)
    stop_event = threading.Event()

    def loop():
        first = True
        while not stop_event.is_set():
            try:
                result = create_backup(
                    database_uri,
                    backup_dir,
                    keep=keep,
                    # Only the start-up run may be skipped as too recent; a due
                    # scheduled run must always write.
                    min_interval_seconds=min_interval if first else None,
                )
                if result.created:
                    app.config['BACKUP_LAST_PATH'] = str(result.path)
                elif result.reason:
                    logger.info('Backup skipped: %s', result.reason)
            except Exception:
                logger.exception('Scheduled backup failed')
            first = False
            stop_event.wait(interval)

    thread = threading.Thread(target=loop, name='EasyOJBackup', daemon=True)
    thread.start()
    app.extensions['easyoj_backup_stop'] = stop_event
    atexit.register(stop_event.set)


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
        # Returning the raw exception rendered an unstyled Werkzeug page with no
        # navigation, which is a dead end for anyone who lands here.
        return _render_error_page(405, t('error.method_not_allowed'))

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
        # Negative cache_size is KiB: 64 MB of page cache instead of the 2 MB default.
        cursor.execute('PRAGMA cache_size=-64000')
        # Ranking and pagination queries sort through a temporary B-tree; keeping
        # those in memory avoids spilling them to disk.
        cursor.execute('PRAGMA temp_store=MEMORY')
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

    def migrate_hot_path_indexes(connection):
        # The dispatcher polls judge_task every tick and every submit resolves
        # contest_problem by problem_id; without these both were full scans.
        statements = (
            'CREATE INDEX IF NOT EXISTS idx_judge_task_status_created '
            'ON judge_task (status, created_at)',
            'CREATE INDEX IF NOT EXISTS idx_judge_task_status_heartbeat '
            'ON judge_task (status, last_heartbeat_at)',
            'CREATE INDEX IF NOT EXISTS idx_submission_submitted_at ON submission (submitted_at)',
            'CREATE INDEX IF NOT EXISTS idx_submission_user_submitted_at '
            'ON submission (user_id, submitted_at)',
            'CREATE INDEX IF NOT EXISTS idx_submission_problem ON submission (problem_id)',
            'CREATE INDEX IF NOT EXISTS idx_contest_problem_problem '
            'ON contest_problem (problem_id)',
            'CREATE INDEX IF NOT EXISTS idx_contest_problem_contest_alias '
            'ON contest_problem (contest_id, alias)',
            'CREATE INDEX IF NOT EXISTS idx_contest_participant_user '
            'ON contest_participant (user_id)',
            'CREATE INDEX IF NOT EXISTS idx_contest_start_time ON contest (start_time)',
            'CREATE INDEX IF NOT EXISTS idx_user_role_active ON user (role, is_active)',
        )
        for statement in statements:
            connection.execute(statement)

    def migrate_contest_problem_aliases(connection):
        # A NULL alias broke url_for and returned 500 for the entire contest page.
        rows = connection.execute(
            'SELECT id, contest_id, display_order FROM contest_problem '
            "WHERE alias IS NULL OR TRIM(alias) = '' ORDER BY contest_id, display_order, id"
        ).fetchall()
        if not rows:
            return
        taken: dict[int, set[str]] = {}
        for contest_id, alias in connection.execute(
            'SELECT contest_id, alias FROM contest_problem '
            "WHERE alias IS NOT NULL AND TRIM(alias) <> ''"
        ).fetchall():
            taken.setdefault(contest_id, set()).add(str(alias).strip().upper())
        for row_id, contest_id, _order in rows:
            used = taken.setdefault(contest_id, set())
            label = next(
                (
                    chr(ord('A') + offset)
                    for offset in range(26)
                    if chr(ord('A') + offset) not in used
                ),
                None,
            )
            if label is None:
                label = next(f'P{n}' for n in range(1, 10000) if f'P{n}' not in used)
            used.add(label)
            connection.execute('UPDATE contest_problem SET alias = ? WHERE id = ?', (label, row_id))

    run_sqlite_migrations(
        db_path,
        [
            migrate_application,
            migrate_submission_idempotency,
            migrate_hot_path_indexes,
            migrate_contest_problem_aliases,
        ],
        timeout_seconds=max(1, app.config.get('SQLITE_BUSY_TIMEOUT_MS', 30000) / 1000),
    )
