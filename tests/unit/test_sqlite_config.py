from app import create_app
from app import db


def test_sqlite_wal_mode_enabled(app):
    with app.app_context():
        result = db.session.execute(db.text('PRAGMA journal_mode')).scalar()
        assert result == 'wal'


def test_sqlite_busy_timeout_set(app):
    with app.app_context():
        result = db.session.execute(db.text('PRAGMA busy_timeout')).scalar()
        assert result >= 5000


def test_sqlite_foreign_keys_enabled(app):
    with app.app_context():
        result = db.session.execute(db.text('PRAGMA foreign_keys')).scalar()
        assert result == 1


def test_sqlite_pragma_configuration_is_idempotent_for_one_app(app):
    from app import _configure_sqlite_pragmas

    with app.app_context():
        _configure_sqlite_pragmas(app)
        _configure_sqlite_pragmas(app)

    with app.app_context():
        result = db.session.execute(db.text('PRAGMA journal_mode')).scalar()
        assert result == 'wal'


def test_sqlite_pragmas_apply_to_every_app_engine(tmp_path):
    apps = []
    for index in (1, 2):
        base_dir = tmp_path / f'base-{index}'
        db_path = base_dir / 'data' / 'database.db'
        db_path.parent.mkdir(parents=True)
        apps.append(
            create_app(
                'testing',
                start_judge_engine=False,
                config_overrides={
                    'BASE_DIR': str(base_dir),
                    'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
                    'SQLITE_BUSY_TIMEOUT_MS': 30000,
                },
            )
        )

    try:
        for created_app in apps:
            with created_app.app_context():
                values = {
                    'journal_mode': db.session.execute(db.text('PRAGMA journal_mode')).scalar(),
                    'busy_timeout': db.session.execute(db.text('PRAGMA busy_timeout')).scalar(),
                    'foreign_keys': db.session.execute(db.text('PRAGMA foreign_keys')).scalar(),
                    'synchronous': db.session.execute(db.text('PRAGMA synchronous')).scalar(),
                }

            assert values == {
                'journal_mode': 'wal',
                'busy_timeout': 30000,
                'foreign_keys': 1,
                'synchronous': 1,
            }
    finally:
        for created_app in apps:
            with created_app.app_context():
                db.session.remove()
                db.engine.dispose()
