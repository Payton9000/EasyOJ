import json
import time

import pytest

from tests.utils import create_problem
from tests.utils import create_user
from tests.utils import write_testcases


def _login(client, username, password):
    return client.post(
        '/login', data={'username': username, 'password': password}, follow_redirects=True
    )


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


def test_python_tle_and_mle(client, app):
    with app.app_context():
        create_user('limit_user', 'limit@example.com')
        problem_tle_id = create_problem('TLE Problem', time_limit=200, memory_limit=128).id
        write_testcases(app.config['BASE_DIR'], problem_tle_id, [('1 2', '3')])
        problem_mle_id = create_problem('MLE Problem', time_limit=800, memory_limit=32).id
        write_testcases(app.config['BASE_DIR'], problem_mle_id, [('1 2', '3')])

    _login(client, 'limit_user', 'password123')

    code_tle = """
while True:
    pass
""".strip()

    res = client.post(
        f'/api/submit/{problem_tle_id}',
        data=json.dumps({'language': 'python', 'code': code_tle}),
        content_type='application/json',
    )
    assert res.status_code == 200
    submission_id = res.get_json()['data']['submission_id']
    result = _poll_submission(client, submission_id, timeout_s=30)
    assert result['status'] in ('TLE', 'RE')

    code_mle = """
data = []
while True:
    data.append(bytearray(5 * 1024 * 1024))
""".strip()

    res = client.post(
        f'/api/submit/{problem_mle_id}',
        data=json.dumps({'language': 'python', 'code': code_mle}),
        content_type='application/json',
    )
    assert res.status_code == 200
    submission_id = res.get_json()['data']['submission_id']
    result = _poll_submission(client, submission_id, timeout_s=30)
    assert result['status'] in ('MLE', 'TLE', 'RE')


def test_compile_error_cpp_and_java(client, app):
    gpp = app.config.get('COMPILER_PATHS', {}).get('g++')
    javac = app.config.get('COMPILER_PATHS', {}).get('javac')

    with app.app_context():
        create_user('compile_user', 'compile@example.com')
        problem = create_problem('CE Problem', time_limit=800, memory_limit=128)
        write_testcases(app.config['BASE_DIR'], problem.id, [('1 2', '3')])

    _login(client, 'compile_user', 'password123')

    if gpp and not pytest.importorskip('os').path.isfile(gpp):
        pytest.skip('g++ not available')

    code_cpp = """
int main(){
    return ;
}
""".strip()

    res = client.post(
        f'/api/submit/{problem.id}',
        data=json.dumps({'language': 'cpp', 'code': code_cpp}),
        content_type='application/json',
    )
    assert res.status_code == 200
    submission_id = res.get_json()['data']['submission_id']
    result = _poll_submission(client, submission_id, timeout_s=10)
    assert result['status'] == 'CE'

    if javac and not pytest.importorskip('os').path.isfile(javac):
        pytest.skip('javac not available')

    code_java = """
public class Main {
    public static void main(String[] args) {
        System.out.println(;
    }
}
""".strip()

    res = client.post(
        f'/api/submit/{problem.id}',
        data=json.dumps({'language': 'java', 'code': code_java}),
        content_type='application/json',
    )
    assert res.status_code == 200
    submission_id = res.get_json()['data']['submission_id']
    result = _poll_submission(client, submission_id, timeout_s=10)
    assert result['status'] == 'CE'
