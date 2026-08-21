from datetime import datetime
from datetime import timedelta

from app import db
from app.models.contest import Contest
from tests.utils import create_problem
from tests.utils import create_user


def _set_locale(client, locale):
    with client.session_transaction() as session:
        session['locale'] = locale


def _login(client, username, password='password123'):
    return client.post(
        '/login',
        data={'username': username, 'password': password},
        follow_redirects=True,
    )


def test_english_problem_and_auth_contract_preserves_database_text(client, app):
    with app.app_context():
        problem = create_problem('题目数据库文本')
        problem_id = problem.id

    login_body = client.get('/login').get_data(as_text=True)
    problem_body = client.get(f'/problem/{problem_id}').get_data(as_text=True)

    assert 'Log in' in login_body
    assert 'Username' in login_body
    assert 'Problems' in problem_body
    assert '题目数据库文本' in problem_body
    assert 'Description' in problem_body


def test_chinese_fixed_text_covers_auth_problem_and_contest_pages(client, app):
    with app.app_context():
        owner = create_user('i18n_ui_owner', 'i18n-ui-owner@example.com')
        problem = create_problem('DB Problem Title')
        contest = Contest(
            title='DB Contest Title',
            description='DB Contest Description',
            start_time=datetime.utcnow() - timedelta(minutes=5),
            end_time=datetime.utcnow() + timedelta(minutes=55),
            is_public=True,
            created_by=owner.id,
        )
        db.session.add(contest)
        db.session.commit()
        problem_id = problem.id

    _set_locale(client, 'zh-CN')
    login_body = client.get('/login').get_data(as_text=True)
    problem_body = client.get('/problems').get_data(as_text=True)
    contest_body = client.get('/contests').get_data(as_text=True)

    assert '登录' in login_body
    assert '用户名' in login_body
    assert '题库' in problem_body
    assert 'DB Problem Title' in problem_body
    assert '竞赛' in contest_body
    assert 'DB Contest Title' in contest_body
    assert '题目描述' not in problem_body
    assert client.get(f'/problem/{problem_id}').status_code == 200


def test_chinese_route_flash_and_error_page_are_translated(client):
    _set_locale(client, 'zh-CN')
    flash_body = client.post(
        '/login',
        data={'username': 'missing-user', 'password': 'wrong-password'},
        follow_redirects=True,
    ).get_data(as_text=True)
    error_body = client.get('/missing-i18n-page').get_data(as_text=True)

    assert '用户名或密码无效' in flash_body
    assert '页面未找到' in error_body
    assert '返回首页' in error_body


def test_english_route_flash_and_error_page_are_translated(client):
    _set_locale(client, 'en')
    flash_body = client.post(
        '/login',
        data={'username': 'missing-user-en', 'password': 'wrong-password'},
        follow_redirects=True,
    ).get_data(as_text=True)
    error_body = client.get('/missing-i18n-page-en').get_data(as_text=True)

    assert 'Invalid username or password.' in flash_body
    assert 'Page not found.' in error_body
    assert 'Back to home' in error_body
