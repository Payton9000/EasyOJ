import os
import sqlite3

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
try:
    from flask_migrate import Migrate
except Exception:
    Migrate = None

from app.config import config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate() if Migrate is not None else None


def create_app(config_name='default', start_judge_engine=True, config_overrides=None):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    if config_overrides:
        app.config.update(config_overrides)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    if migrate is not None:
        migrate.init_app(app, db)

    login_manager.login_view = 'web.login'
    login_manager.login_message_category = 'error'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return User.query.get(int(user_id))

    # Register blueprints
    from app.web import web_bp, admin_bp
    app.register_blueprint(web_bp)
    app.register_blueprint(admin_bp)

    from app.api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    from app.judge import judge_bp
    app.register_blueprint(judge_bp, url_prefix='/judge')

    with app.app_context():
        db.create_all()
        _ensure_judge_task_columns(app)
        _ensure_submission_indexes(app)

    # Initialize and start judge engine
    from app.judge.engine import JudgeEngine
    judge_engine = JudgeEngine(app, config_name=config_name)
    app.judge_engine = judge_engine

    if start_judge_engine and not app.config.get('TESTING'):
        judge_engine.start()

    @app.teardown_appcontext
    def shutdown_judge_engine(exception=None):
        pass  # Engine runs as daemon threads; stop on process exit

    return app


def _ensure_judge_task_columns(app):
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite:///'):
        return

    db_path = db_uri.replace('sqlite:///', '')
    if not os.path.isfile(db_path):
        return

    columns_to_add = {
        'last_heartbeat_at': 'DATETIME',
        'retry_count': 'INTEGER DEFAULT 0',
        'last_error': 'TEXT',
        'debug_log_path': 'VARCHAR(255)',
    }

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info('judge_task');")
        existing = {row[1] for row in cursor.fetchall()}

        for name, column_type in columns_to_add.items():
            if name not in existing:
                cursor.execute(f"ALTER TABLE judge_task ADD COLUMN {name} {column_type};")
        conn.commit()
    except sqlite3.Error:
        if conn is not None:
            conn.rollback()
    finally:
        if conn is not None:
            conn.close()


def _ensure_submission_indexes(app):
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite:///'):
        return

    db_path = db_uri.replace('sqlite:///', '')
    if not os.path.isfile(db_path):
        return

    create_index_sql = [
        (
            'idx_contest_problem_status',
            'CREATE INDEX IF NOT EXISTS idx_contest_problem_status '
            'ON submission (contest_id, problem_id, status);',
        ),
        (
            'idx_contest_user_submitted_at',
            'CREATE INDEX IF NOT EXISTS idx_contest_user_submitted_at '
            'ON submission (contest_id, user_id, submitted_at);',
        ),
    ]

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        for _, sql in create_index_sql:
            cursor.execute(sql)
        conn.commit()
    except sqlite3.Error:
        if conn is not None:
            conn.rollback()
    finally:
        if conn is not None:
            conn.close()
