import json

from tests.utils import create_problem
from tests.utils import create_user
from tests.utils import write_testcases


def _login(client, username, password):
    return client.post(
        '/login', data={'username': username, 'password': password}, follow_redirects=True
    )


def test_api_submit_requires_csrf_header_when_enabled(client, app, monkeypatch):
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        with app.app_context():
            create_user('csrf_api_user', 'csrf_api@example.com')
            problem = create_problem('CSRF API Test')
            problem_id = problem.id
            write_testcases(app.config['BASE_DIR'], problem_id, [('1 2', '3')])

        login_page = client.get('/login')
        assert login_page.status_code == 200
        import re

        match = re.search(rb'name="csrf_token" value="([^"]+)"', login_page.data)
        assert match, 'CSRF token not found in login page'
        csrf_token = match.group(1).decode()

        client.post(
            '/login',
            data={
                'username': 'csrf_api_user',
                'password': 'password123',
                'csrf_token': csrf_token,
            },
            follow_redirects=True,
        )

        token_response = client.get('/api/csrf-token')
        assert token_response.status_code == 200
        csrf_token = token_response.get_json()['data']['csrf_token']

        monkeypatch.setattr(app.judge_engine, 'submit_judge_task', lambda submission_id: True)

        missing_token = client.post(
            f'/api/submit/{problem_id}',
            data=json.dumps({'language': 'python', 'code': 'print(3)'}),
            content_type='application/json',
        )
        assert missing_token.status_code == 400
        assert missing_token.is_json
        assert missing_token.get_json() == {
            'code': 400,
            'message': 'CSRF token missing or invalid',
        }

        accepted = client.post(
            f'/api/submit/{problem_id}',
            data=json.dumps({'language': 'python', 'code': 'print(3)'}),
            content_type='application/json',
            headers={'X-CSRFToken': csrf_token},
        )
        assert accepted.status_code == 200
        assert accepted.get_json()['code'] == 0
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_api_404_returns_json(client, app):
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        res = client.get('/api/nonexistent')
        assert res.status_code == 404
        assert res.is_json
        data = res.get_json()
        assert data['code'] == 404
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_api_unknown_problem_returns_json_404(client, app):
    with app.app_context():
        create_user('json404_user', 'json404@example.com')

    _login(client, 'json404_user', 'password123')

    res = client.get('/api/problems/999999')
    assert res.status_code == 404
    assert res.is_json
    assert res.get_json()['code'] == 404
