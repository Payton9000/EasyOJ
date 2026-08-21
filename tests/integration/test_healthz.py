from app import create_app


def test_healthz_is_not_ready_without_running_judge_engine(tmp_path):
    db_path = tmp_path / 'health.db'
    app = create_app(
        'testing',
        start_judge_engine=False,
        config_overrides={'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}'},
    )
    response = app.test_client().get('/healthz')

    assert response.status_code == 503
    assert response.get_json() == {
        'service': 'easyoj',
        'status': 'not_ready',
        'version': 1,
    }


def test_healthz_returns_stable_ready_marker_when_dependencies_are_ready(app):
    response = app.test_client().get('/healthz')

    assert response.status_code == 200
    assert response.get_json() == {
        'service': 'easyoj',
        'status': 'ok',
        'version': 1,
    }
