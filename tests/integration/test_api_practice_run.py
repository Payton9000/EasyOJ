import json

from tests.utils import create_problem
from tests.utils import create_user
from tests.utils import write_testcases


def _login(client, username):
    return client.post(
        '/login',
        data={'username': username, 'password': 'password123'},
        follow_redirects=True,
    )


def test_practice_run_executes_code_without_creating_submission(client, app):
    with app.app_context():
        user = create_user('practice_api_user', 'practice_api_user@example.com')
        username = user.username
        problem = create_problem('Practice API Problem')
        write_testcases(app.config['BASE_DIR'], problem.id, [('1', '1')])
        problem_id = problem.id

    _login(client, username)
    response = client.post(
        f'/api/run/{problem_id}',
        data=json.dumps({'language': 'python', 'code': 'print(input())', 'input': '42\n'}),
        content_type='application/json',
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['code'] == 0
    assert payload['data']['status'] == 'OK'
    assert payload['data']['output'].strip() == '42'


def test_practice_run_requires_login(client, app):
    with app.app_context():
        problem = create_problem('Practice Auth Problem')
        problem_id = problem.id

    response = client.post(
        f'/api/run/{problem_id}',
        data=json.dumps({'language': 'python', 'code': 'print(1)', 'input': ''}),
        content_type='application/json',
    )

    assert response.status_code == 401
