import os
from pathlib import Path

import pytest

from app import create_app, db
from app.config import TestingConfig


def _repo_base():
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope='session')
def app(tmp_path_factory):
    base_dir = tmp_path_factory.mktemp('base')
    (base_dir / 'data').mkdir(parents=True, exist_ok=True)
    db_path = tmp_path_factory.mktemp('db') / 'test.db'

    TestingConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"

    app = create_app(
        'testing',
        config_overrides={
            'BASE_DIR': str(base_dir),
            'SQLALCHEMY_DATABASE_URI': f"sqlite:///{db_path}",
        },
    )
    app.config['MAX_JUDGE_WORKERS'] = 2
    app.config['JUDGE_QUEUE_MAXSIZE'] = 200

    with app.app_context():
        db.drop_all()
        db.create_all()

    app.judge_engine.start()

    yield app

    app.judge_engine.stop()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db_session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
