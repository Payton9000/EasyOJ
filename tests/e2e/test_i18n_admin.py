from app.models.user import User
from tests.utils import create_user


def _set_locale(client, locale):
    with client.session_transaction() as session:
        session['locale'] = locale


def _login_admin(client, app):
    with app.app_context():
        user = User.query.filter_by(username='i18n_admin').first()
        if user is None:
            user = create_user('i18n_admin', 'i18n-admin@example.com', role='admin')
        username = user.username
    response = client.post(
        '/login',
        data={'username': username, 'password': 'password123'},
        follow_redirects=True,
    )
    assert response.status_code == 200


def test_admin_pages_have_english_fixed_text(client, app):
    _login_admin(client, app)
    _set_locale(client, 'en')

    for path in (
        '/admin/dashboard',
        '/admin/problems',
        '/admin/contests',
        '/admin/users',
        '/admin/submissions',
        '/admin/judge_status',
    ):
        body = client.get(path).get_data(as_text=True)
        assert 'Administration' in body
        assert 'Dashboard' in body
        assert 'Problems' in body

    assert 'Judge monitor' in client.get('/admin/judge_status').get_data(as_text=True)


def test_admin_pages_have_chinese_fixed_text_and_keep_route_access(client, app):
    _login_admin(client, app)
    _set_locale(client, 'zh-CN')

    dashboard = client.get('/admin/dashboard').get_data(as_text=True)
    users = client.get('/admin/users').get_data(as_text=True)
    problems = client.get('/admin/problems').get_data(as_text=True)
    contests = client.get('/admin/contests').get_data(as_text=True)
    submissions = client.get('/admin/submissions').get_data(as_text=True)
    judge_status = client.get('/admin/judge_status').get_data(as_text=True)

    assert '管理后台' in dashboard
    assert '仪表盘' in dashboard
    assert '用户管理' in users
    assert '题目管理' in problems
    assert '竞赛管理' in contests
    assert '提交记录' in submissions
    assert '判题监控' in judge_status
    assert 'Administration' not in dashboard


def test_admin_validation_flash_is_translated(client, app):
    _login_admin(client, app)
    _set_locale(client, 'en')
    english = client.post('/admin/problem/create', data={}, follow_redirects=True).get_data(
        as_text=True
    )
    _set_locale(client, 'zh-CN')
    chinese = client.post('/admin/problem/create', data={}, follow_redirects=True).get_data(
        as_text=True
    )

    assert 'Title and description are required.' in english
    assert '标题和描述不能为空' in chinese
