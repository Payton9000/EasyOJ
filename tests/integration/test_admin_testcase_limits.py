import shutil
from io import BytesIO
from pathlib import Path

from app import db
from app.models.problem import Problem
from app.models.user import User


def _create_admin(app, username='limits_admin'):
    with app.app_context():
        user = User(
            username=username,
            email=f'{username}@example.com',
            role='admin',
            is_active=True,
        )
        user.set_password('Password123!')
        db.session.add(user)
        db.session.commit()
        problem = Problem(title=f'{username} problem', description='test', created_by=user.id)
        db.session.add(problem)
        db.session.commit()
        # This test shares one app fixture; remove only the exact storage path
        # for the newly-created problem in case a prior attempt left artifacts.
        testcase_dir = Path(app.config['BASE_DIR']) / 'data' / 'problems' / str(problem.id)
        if testcase_dir.exists():
            shutil.rmtree(testcase_dir)
        return problem.id


def _login(client, username):
    return client.post(
        '/login',
        data={'username': username, 'password': 'Password123!'},
        follow_redirects=False,
    )


def _upload(
    client, problem_id, input_name='1.in', output_name='1.out', input_data=b'1', output_data=b'1'
):
    return client.post(
        f'/admin/problem/{problem_id}/upload_testcase',
        data={
            'input_file': (BytesIO(input_data), input_name),
            'output_file': (BytesIO(output_data), output_name),
        },
        content_type='multipart/form-data',
        follow_redirects=False,
    )


def _files(app, problem_id):
    directory = Path(app.config['BASE_DIR']) / 'data' / 'problems' / str(problem_id) / 'testcases'
    return sorted(path.name for path in directory.iterdir()) if directory.exists() else []


def test_upload_rejects_oversized_input_without_partial_files(client, app, monkeypatch):
    problem_id = _create_admin(app, 'size_limits_admin')
    _login(client, 'size_limits_admin')
    monkeypatch.setitem(app.config, 'TESTCASE_MAX_INPUT_BYTES', 3)

    response = _upload(client, problem_id, input_data=b'1234', output_data=b'1')

    assert response.status_code == 302
    assert _files(app, problem_id) == []


def test_upload_rejects_path_traversal_filename_without_partial_files(client, app):
    problem_id = _create_admin(app, 'filename_limits_admin')
    _login(client, 'filename_limits_admin')

    response = _upload(client, problem_id, input_name='../escape.in')

    assert response.status_code == 302
    assert _files(app, problem_id) == []


def test_upload_enforces_case_and_problem_quota(client, app, monkeypatch):
    problem_id = _create_admin(app, 'quota_limits_admin')
    _login(client, 'quota_limits_admin')
    for key, value in {
        'TESTCASE_MAX_COUNT': 1,
        'TESTCASE_MAX_PROBLEM_BYTES': 4,
        'TESTCASE_MAX_INPUT_BYTES': 4,
        'TESTCASE_MAX_OUTPUT_BYTES': 4,
    }.items():
        monkeypatch.setitem(app.config, key, value)

    assert _upload(client, problem_id, input_data=b'12', output_data=b'34').status_code == 302
    assert _upload(client, problem_id, input_data=b'5', output_data=b'6').status_code == 302
    assert len([name for name in _files(app, problem_id) if name.endswith('.in')]) == 1


def test_upload_rejects_when_global_quota_would_be_exceeded(client, app, monkeypatch):
    problem_id = _create_admin(app, 'global_limits_admin')
    _login(client, 'global_limits_admin')
    for key, value in {
        'TESTCASE_MAX_GLOBAL_BYTES': 5,
        'TESTCASE_MAX_PROBLEM_BYTES': 100,
        'TESTCASE_MAX_INPUT_BYTES': 4,
        'TESTCASE_MAX_OUTPUT_BYTES': 4,
    }.items():
        monkeypatch.setitem(app.config, key, value)

    response = _upload(client, problem_id, input_data=b'123', output_data=b'123')

    assert response.status_code == 302
    assert _files(app, problem_id) == []
