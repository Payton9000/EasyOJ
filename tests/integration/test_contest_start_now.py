from datetime import datetime
from datetime import timedelta

from app.models.contest import Contest
from tests.utils import create_user


def _login(client, username):
    return client.post('/login', data={'username': username, 'password': 'password123'})


def test_start_now_creates_a_running_contest(client, app):
    with app.app_context():
        admin = create_user('start_now_admin', 'start-now-admin@example.com', role='admin')
        username = admin.username

    _login(client, username)
    later = (datetime.now() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')
    response = client.post(
        '/admin/contest/create',
        data={
            'title': 'Start Now Contest',
            'description': '',
            'end_time': later,
            'max_participants': '0',
            'is_public': 'on',
            'start_now': '1',
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        contest = Contest.query.filter_by(title='Start Now Contest').one()
        assert contest.status == 'Running'
        assert contest.start_time <= datetime.utcnow() + timedelta(seconds=5)


def test_start_now_validation_error_keeps_immediate_start_intent(client, app):
    with app.app_context():
        admin = create_user('start_now_retry_admin', 'start-now-retry@example.com', role='admin')
        username = admin.username

    _login(client, username)
    later = (datetime.now() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')
    body = client.post(
        '/admin/contest/create',
        data={
            'title': '',
            'end_time': later,
            'max_participants': '0',
            'is_public': 'on',
            'start_now': '1',
        },
    ).get_data(as_text=True)

    assert 'name="start_now"' in body
    assert 'id="cf-start"' in body
    start_value = body.split('id="cf-start"', 1)[1].split('value="', 1)[1].split('"', 1)[0]
    assert start_value


def test_editing_started_contest_does_not_warn_when_start_minute_is_unchanged(client, app):
    with app.app_context():
        admin = create_user('start_now_edit_admin', 'start-now-edit@example.com', role='admin')
        username = admin.username

    _login(client, username)
    later = (datetime.now() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')
    client.post(
        '/admin/contest/create',
        data={
            'title': 'Start Now Edit',
            'end_time': later,
            'max_participants': '0',
            'is_public': 'on',
            'start_now': '1',
        },
    )
    with app.app_context():
        contest_id = Contest.query.filter_by(title='Start Now Edit').one().id

    edit_page = client.get(f'/admin/contest/{contest_id}/edit').get_data(as_text=True)
    start_raw = edit_page.split('id="cf-start"', 1)[1].split('value="', 1)[1].split('"', 1)[0]
    end_raw = edit_page.split('id="cf-end"', 1)[1].split('value="', 1)[1].split('"', 1)[0]
    response = client.post(
        f'/admin/contest/{contest_id}/edit',
        data={
            'title': 'Start Now Edit',
            'description': 'updated',
            'start_time': start_raw,
            'end_time': end_raw,
            'max_participants': '0',
            'is_public': 'on',
        },
        follow_redirects=True,
    )

    assert 'cannot change its start time' not in response.get_data(as_text=True).lower()
    assert '不能改变' not in response.get_data(as_text=True)


def test_contest_create_form_exposes_start_now_and_late_signup_controls(client, app):
    with app.app_context():
        admin = create_user('contest_form_admin', 'contest-form-admin@example.com', role='admin')
        username = admin.username

    _login(client, username)
    body = client.get('/admin/contest/create').get_data(as_text=True)

    assert 'id="contest-start-now"' in body
    assert 'data-action="start-now"' in body
    assert 'name="close_registration_at_start"' in body
    assert 'id="login-submit"' not in body


def test_admin_root_redirects_to_dashboard(client, app):
    with app.app_context():
        admin = create_user('dash_redirect_admin', 'dash-redirect@example.com', role='admin')
        username = admin.username

    _login(client, username)
    response = client.get('/admin/', follow_redirects=False)

    assert response.status_code in {301, 302}
    assert response.headers['Location'].rstrip('/').endswith('/admin/dashboard')
