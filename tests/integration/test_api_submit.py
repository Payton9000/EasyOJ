import json
import time

from app import db
from tests.utils import create_user, create_problem, write_testcases


def _login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)


def _poll_submission(client, submission_id, timeout_s=10):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        res = client.get(f'/api/submission/{submission_id}')
        data = res.get_json()
        status = data['data']['status']
        if status not in ('Pending', 'Queued', 'Judging'):
            return data['data']
        time.sleep(0.2)
    return data['data']


def test_submit_ac_and_wa(client, app):
    with app.app_context():
        user = create_user('tester1', 'tester1@example.com')
        problem_id = create_problem('Sum Test').id
        write_testcases(app.config['BASE_DIR'], problem_id, [('1 2', '3'), ('10 20', '30')])

    _login(client, 'tester1', 'password123')

    code_ac = """
import sys
nums = list(map(int, sys.stdin.read().strip().split()))
if nums:
    print(sum(nums))
""".strip()

    res = client.post(
        f'/api/submit/{problem_id}',
        data=json.dumps({'language': 'python', 'code': code_ac}),
        content_type='application/json',
    )
    assert res.status_code == 200
    submission_id = res.get_json()['data']['submission_id']

    result = _poll_submission(client, submission_id)
    assert result['status'] == 'AC'

    code_wa = """
print(0)
""".strip()

    res = client.post(
        f'/api/submit/{problem_id}',
        data=json.dumps({'language': 'python', 'code': code_wa}),
        content_type='application/json',
    )
    assert res.status_code == 200
    submission_id = res.get_json()['data']['submission_id']

    result = _poll_submission(client, submission_id)
    assert result['status'] == 'WA'
