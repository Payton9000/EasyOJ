from datetime import datetime
from datetime import timedelta
from datetime import timezone

from app import db
from app.models.contest import Contest
from tests.utils import create_user


def _login(client, username):
    return client.post('/login', data={'username': username, 'password': 'password123'})


def test_contest_time_edit_round_trip_and_public_display_use_local_time(client, app):
    original_timezone = app.config.get('LOCAL_TIMEZONE')
    app.config['LOCAL_TIMEZONE'] = timezone(timedelta(hours=8))
    try:
        with app.app_context():
            admin = create_user('time_roundtrip_admin', 'time-roundtrip@example.com', role='admin')
            contest = Contest(
                title='Local Time Round Trip',
                start_time=datetime(2035, 6, 15, 1, 30),
                end_time=datetime(2035, 6, 15, 3, 30),
                is_public=True,
                created_by=admin.id,
            )
            db.session.add(contest)
            db.session.commit()
            contest_id = contest.id

        _login(client, 'time_roundtrip_admin')
        edit_page = client.get(f'/admin/contest/{contest_id}/edit')
        edit_html = edit_page.get_data(as_text=True)
        assert 'value="2035-06-15T09:30"' in edit_html
        assert 'value="2035-06-15T11:30"' in edit_html

        update = client.post(
            f'/admin/contest/{contest_id}/edit',
            data={
                'title': 'Local Time Round Trip',
                'description': '',
                'start_time': '2035-06-15T09:30',
                'end_time': '2035-06-15T11:30',
                'max_participants': '0',
                'is_public': 'on',
            },
        )
        assert update.status_code == 302

        with app.app_context():
            contest = db.session.get(Contest, contest_id)
            assert contest.start_time == datetime(2035, 6, 15, 1, 30)
            assert contest.end_time == datetime(2035, 6, 15, 3, 30)

        public_page = client.get('/contests')
        public_html = public_page.get_data(as_text=True)
        assert '2035-06-15 09:30' in public_html
        assert '2035-06-15 11:30' in public_html
    finally:
        if original_timezone is None:
            app.config.pop('LOCAL_TIMEZONE', None)
        else:
            app.config['LOCAL_TIMEZONE'] = original_timezone
