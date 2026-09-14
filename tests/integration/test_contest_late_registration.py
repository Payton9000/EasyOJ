from datetime import datetime
from datetime import timedelta

from app import db
from app.models.contest import Contest
from app.models.contest_participant import ContestParticipant
from tests.utils import create_problem
from tests.utils import create_user


def _login(client, username):
    return client.post('/login', data={'username': username, 'password': 'password123'})


def test_student_can_register_after_contest_starts(client, app):
    with app.app_context():
        admin = create_user('late_reg_admin', 'late-reg-admin@example.com', role='admin')
        student = create_user('late_reg_student', 'late-reg-student@example.com')
        create_problem('Late Registration Problem')
        now = datetime.utcnow()
        contest = Contest(
            title='Late Registration Contest',
            start_time=now - timedelta(minutes=5),
            end_time=now + timedelta(hours=1),
            is_public=True,
            created_by=admin.id,
            close_registration_at_start=False,
        )
        db.session.add(contest)
        db.session.commit()
        contest_id = contest.id
        student_name = student.username
        student_id = student.id

    _login(client, student_name)
    response = client.post(f'/contest/{contest_id}/register', follow_redirects=False)

    assert response.status_code == 302
    with app.app_context():
        assert (
            ContestParticipant.query.filter_by(contest_id=contest_id, user_id=student_id).first()
            is not None
        )


def test_student_cannot_register_when_teacher_closes_late_signup(client, app):
    with app.app_context():
        admin = create_user('closed_reg_admin', 'closed-reg-admin@example.com', role='admin')
        student = create_user('closed_reg_student', 'closed-reg-student@example.com')
        now = datetime.utcnow()
        contest = Contest(
            title='Closed Registration Contest',
            start_time=now - timedelta(minutes=5),
            end_time=now + timedelta(hours=1),
            is_public=True,
            created_by=admin.id,
            close_registration_at_start=True,
        )
        db.session.add(contest)
        db.session.commit()
        contest_id = contest.id
        student_name = student.username

    _login(client, student_name)
    response = client.post(f'/contest/{contest_id}/register', follow_redirects=True)

    assert response.status_code == 200
    assert b'registration' in response.data.lower() or '报名' in response.get_data(as_text=True)
    with app.app_context():
        assert ContestParticipant.query.filter_by(contest_id=contest_id).count() == 0
