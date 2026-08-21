import importlib

from app import create_app
from app import db
from app.models.problem import Problem
from app.models.user import User
from problem_bank.catalog import get_specs


def test_init_db_installs_builtin_problem_bank_without_starting_workers(tmp_path, monkeypatch):
    module = importlib.import_module('init_db')
    base_dir = tmp_path / 'base'
    db_path = tmp_path / 'database.sqlite'
    app = create_app(
        'testing',
        start_judge_engine=False,
        config_overrides={
            'BASE_DIR': str(base_dir),
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        },
    )
    with app.app_context():
        db.drop_all()
        db.create_all()

    monkeypatch.setattr(module, 'create_app', lambda *args, **kwargs: app)
    monkeypatch.setenv('EASYOJ_INITIAL_ADMIN_PASSWORD', 'InitStrong!2345')

    module.init_db()

    with app.app_context():
        admin = User.query.filter_by(username='admin').one()
        expected_titles = {spec.title for spec in get_specs()}
        installed = Problem.query.filter(Problem.title.in_(expected_titles)).all()

        assert admin.must_change_password is True
        assert len(installed) == 30
        assert all(problem.created_by == admin.id for problem in installed)
        assert all(problem.test_case_count >= 10 for problem in installed)
        assert app.judge_engine.is_running is False
