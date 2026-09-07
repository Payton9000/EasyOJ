import importlib

import pytest

from app import db
from app.models.user import User


def _account_service():
    try:
        return importlib.import_module('app.services.account_service').AccountService
    except (ImportError, AttributeError) as exc:
        pytest.fail(f'account service is not implemented yet: {exc}')


def test_register_normalizes_username_and_email(client, app):
    response = client.post(
        '/register',
        data={
            'username': '  Student_01  ',
            'email': '  Student@Example.COM ',
            'password': 'abc12345',
            'confirm_password': 'abc12345',
        },
    )

    assert response.status_code == 302
    with app.app_context():
        user = User.query.filter_by(username='student_01').first()
        assert user is not None
        assert user.email == 'student@example.com'


def test_register_rejects_duplicate_after_normalization(client, app):
    with app.app_context():
        user = User(username='duplicate_user', email='duplicate@example.com')
        user.set_password('abc12345')
        db.session.add(user)
        db.session.commit()

    response = client.post(
        '/register',
        data={
            'username': ' DUPLICATE_USER ',
            'email': 'other@example.com',
            'password': 'abc12345',
            'confirm_password': 'abc12345',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'already' in response.data.lower() or b'taken' in response.data.lower()


def test_login_accepts_legacy_mixed_case_username(client, app):
    with app.app_context():
        user = User(username='LegacyUser', email='legacy-user@example.com')
        user.set_password('abc12345')
        db.session.add(user)
        db.session.commit()

    response = client.post('/login', data={'username': 'legacyuser', 'password': 'abc12345'})

    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session['_user_id']


def test_login_preserves_selected_locale(client, app):
    with app.app_context():
        user = User(username='locale_user', email='locale-user@example.com')
        user.set_password('abc12345')
        db.session.add(user)
        db.session.commit()

    client.post('/language/zh-CN')
    response = client.post(
        '/login',
        data={'username': 'locale_user', 'password': 'abc12345'},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert '<html lang="zh-CN">' in response.get_data(as_text=True)
    with client.session_transaction() as session:
        assert session['locale'] == 'zh-CN'


def test_register_rejects_seven_character_password(client, app):
    response = client.post(
        '/register',
        data={
            'username': 'short_password_user',
            'email': 'short-password@example.com',
            'password': 'abc1234',
            'confirm_password': 'abc1234',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        assert User.query.filter_by(username='short_password_user').first() is None


def test_inactive_user_cannot_login(client, app):
    with app.app_context():
        user = User(username='inactive_user', email='inactive@example.com', is_active=False)
        user.set_password('abc12345')
        db.session.add(user)
        db.session.commit()

    response = client.post(
        '/login',
        data={'username': 'inactive_user', 'password': 'abc12345'},
        follow_redirects=True,
    )

    assert response.status_code == 200
    # A disabled account now says so. Claiming the password is invalid sent students
    # to ask for a password reset that could not fix anything.
    assert b'disabled' in response.data.lower()
    with client.session_transaction() as session:
        assert '_user_id' not in session


def test_login_is_locked_after_repeated_failures(client, app):
    app.config['LOGIN_MAX_FAILURES'] = 2
    app.extensions.pop('login_rate_limiter', None)
    with app.app_context():
        user = User(username='locked_user', email='locked@example.com')
        user.set_password('abc12345')
        db.session.add(user)
        db.session.commit()

    for _ in range(2):
        client.post('/login', data={'username': 'locked_user', 'password': 'wrong'})

    response = client.post(
        '/login',
        data={'username': 'locked_user', 'password': 'abc12345'},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with client.session_transaction() as session:
        assert '_user_id' not in session


def test_logout_is_post_only(client, app):
    with app.app_context():
        user = User(username='logout_user', email='logout@example.com')
        user.set_password('abc12345')
        db.session.add(user)
        db.session.commit()

    client.post('/login', data={'username': 'logout_user', 'password': 'abc12345'})
    assert client.get('/logout').status_code == 405


def test_browser_post_requires_csrf_token(client, app):
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        response = client.post(
            '/register',
            data={
                'username': 'csrf_user',
                'email': 'csrf@example.com',
                'password': 'abc12345',
                'confirm_password': 'abc12345',
            },
        )
        assert response.status_code == 400
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_login_next_rejects_protocol_relative_url(client, app):
    with app.app_context():
        user = User(username='next_safe', email='next_safe@example.com')
        user.set_password('abc12345')
        db.session.add(user)
        db.session.commit()

    response = client.post(
        '/login?next=//evil.com', data={'username': 'next_safe', 'password': 'abc12345'}
    )
    assert response.status_code == 302
    location = response.headers.get('Location', '')
    assert 'evil.com' not in location


def test_login_next_accepts_local_path(client, app):
    with app.app_context():
        user = User(username='next_local', email='next_local@example.com')
        user.set_password('abc12345')
        db.session.add(user)
        db.session.commit()

    response = client.post(
        '/login?next=/problems', data={'username': 'next_local', 'password': 'abc12345'}
    )
    assert response.status_code == 302
    assert response.headers.get('Location', '').endswith('/problems')
