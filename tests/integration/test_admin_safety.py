import importlib
from datetime import datetime
from datetime import timedelta
from io import BytesIO

import pytest

from app import db
from app.models.user import User


def _account_service():
    try:
        return importlib.import_module('app.services.account_service').AccountService
    except (ImportError, AttributeError) as exc:
        pytest.fail(f'account service is not implemented yet: {exc}')


def _create_admin(username, email):
    user = User(username=username, email=email, role='admin')
    user.set_password('abc12345')
    db.session.add(user)
    db.session.commit()
    return user


def _login_admin(client, username):
    response = client.post('/login', data={'username': username, 'password': 'abc12345'})
    assert response.status_code == 302


def test_admin_cannot_disable_self(client, app):
    with app.app_context():
        admin = _create_admin('self_admin', 'self-admin@example.com')
        admin_id = admin.id

    _login_admin(client, 'self_admin')
    response = client.post(f'/admin/user/{admin_id}/toggle_active')

    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(User, admin_id).is_active is True


def test_only_last_active_admin_cannot_be_disabled(app):
    AccountService = _account_service()
    with app.app_context():
        admin = _create_admin('only_admin', 'only-admin@example.com')
        assert AccountService.can_change_admin_state(admin, actor=admin, active=False) is False


def test_password_reset_is_one_time_and_forces_change(client, app):
    with app.app_context():
        _create_admin('reset_admin', 'reset-admin@example.com')
        target = User(username='reset_target', email='reset-target@example.com')
        target.set_password('abc12345')
        db.session.add(target)
        db.session.commit()
        target_id = target.id

    _login_admin(client, 'reset_admin')
    response = client.post(f'/admin/user/{target_id}/reset_password')

    assert response.status_code == 200
    assert b'data-reset-password' in response.data
    with app.app_context():
        assert db.session.get(User, target_id).must_change_password is True

    follow_up = client.get('/admin/users')
    assert b'data-reset-password' not in follow_up.data


def test_disabled_user_session_is_revoked_on_next_request(client, app):
    with app.app_context():
        admin = _create_admin('disable_admin', 'disable-admin@example.com')
        user = User(username='disable_target', email='disable-target@example.com')
        user.set_password('abc12345')
        db.session.add(user)
        db.session.commit()
        admin_id = admin.id
        user_id = user.id

    user_client = app.test_client()
    _login_admin(user_client, 'disable_target')

    _login_admin(client, 'disable_admin')
    response = client.post(f'/admin/user/{user_id}/toggle_active')
    assert response.status_code == 302

    browser_response = user_client.get('/submissions', follow_redirects=False)
    assert browser_response.status_code == 302
    assert '/login' in browser_response.headers['Location']

    api_response = user_client.get('/api/submissions')
    assert api_response.status_code == 401

    with app.app_context():
        assert db.session.get(User, admin_id).is_active is True


def test_reset_password_forces_existing_session_to_change_password(client, app):
    with app.app_context():
        _create_admin('force_admin', 'force-admin@example.com')
        user = User(username='force_target', email='force-target@example.com')
        user.set_password('abc12345')
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    user_client = app.test_client()
    _login_admin(user_client, 'force_target')
    _login_admin(client, 'force_admin')
    response = client.post(f'/admin/user/{user_id}/reset_password')
    assert response.status_code == 200

    browser_response = user_client.get('/submissions', follow_redirects=False)
    assert browser_response.status_code == 302
    assert '/change-password' in browser_response.headers['Location']


def test_admin_input_limits_are_normalized(client, app):
    with app.app_context():
        _create_admin('input_admin', 'input-admin@example.com')

    _login_admin(client, 'input_admin')
    problem_response = client.post(
        '/admin/problem/create',
        data={
            'title': 'Validated problem',
            'description': 'Description',
            'difficulty': 'unexpected',
            'time_limit': '1000',
            'memory_limit': '256',
        },
    )
    assert problem_response.status_code == 302

    with app.app_context():
        from app.models.problem import Problem

        problem = Problem.query.filter_by(title='Validated problem').one()
        assert problem.difficulty == 'medium'


def test_negative_contest_capacity_is_rejected_and_input_is_preserved(client, app):
    """An out-of-range cap must be reported, not silently rewritten.

    It used to be clamped to 0 (unlimited) while the page still reported success,
    so an organiser had no way to notice their value had been replaced.
    """
    with app.app_context():
        _create_admin('contest_input_admin', 'contest-input@example.com')

    _login_admin(client, 'contest_input_admin')
    start = (datetime.now() + timedelta(hours=2)).replace(microsecond=0)
    end = start + timedelta(hours=2)
    response = client.post(
        '/admin/contest/create',
        data={
            'title': 'Capacity validation',
            'start_time': start.isoformat(timespec='minutes'),
            'end_time': end.isoformat(timespec='minutes'),
            'max_participants': '-10',
        },
    )
    assert response.status_code == 200
    # The rejected form comes back carrying what the organiser typed.
    assert 'Capacity validation' in response.get_data(as_text=True)

    with app.app_context():
        from app.models.contest import Contest

        assert Contest.query.filter_by(title='Capacity validation').first() is None


def test_testcase_upload_with_missing_filenames_is_rejected_cleanly(client, app):
    with app.app_context():
        admin = _create_admin('upload_admin', 'upload-admin@example.com')
        from app.models.problem import Problem

        problem = Problem(title='Upload target', description='Description', created_by=admin.id)
        db.session.add(problem)
        db.session.commit()
        problem_id = problem.id

    _login_admin(client, 'upload_admin')
    response = client.post(
        f'/admin/problem/{problem_id}/upload_testcase',
        data={
            'input_file': (BytesIO(b'1'), ''),
            'output_file': (BytesIO(b'1'), ''),
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 302
