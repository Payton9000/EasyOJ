import os
import tempfile

from app import create_app


def test_500_handler_does_not_recurse(monkeypatch):
    base = tempfile.mkdtemp()
    app = create_app(
        'testing',
        start_judge_engine=False,
        config_overrides={
            'BASE_DIR': base,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + os.path.join(base, 't.db'),
            'SANDBOX_APP_CONTAINER': False,
            'PROPAGATE_EXCEPTIONS': False,
        },
    )

    @app.route('/boom')
    def boom():
        raise RuntimeError('boom')

    def broken_render(*args, **kwargs):
        raise RuntimeError('template broke')

    import app as easyoj_app_module

    monkeypatch.setattr(easyoj_app_module, 'render_template', broken_render)

    response = app.test_client().get('/boom')
    assert response.status_code == 500
    assert b'500' in response.data
