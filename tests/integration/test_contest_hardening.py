from datetime import datetime
from datetime import timedelta

from werkzeug.security import check_password_hash

from app import db
from app.models.contest import Contest
from app.models.contest_participant import ContestParticipant
from app.models.contest_problem import ContestProblem
from app.models.submission import Submission
from tests.utils import create_problem
from tests.utils import create_user


def _login(client, username, password='password123'):
    return client.post(
        '/login', data={'username': username, 'password': password}, follow_redirects=True
    )


def _contest(app, *, user, problem, password=None, ended=False, pending=False):
    now = datetime.utcnow()
    start = now + timedelta(hours=1) if pending else now - timedelta(hours=2)
    end = now - timedelta(hours=1) if ended else now + timedelta(hours=1)
    contest = Contest(
        title='Hardening Contest',
        start_time=start,
        end_time=end,
        is_public=True,
        created_by=user.id,
        password=password,
    )
    db.session.add(contest)
    db.session.flush()
    contest_problem = ContestProblem(
        contest_id=contest.id,
        problem_id=problem.id,
        alias='A',
        display_order=1,
    )
    db.session.add(contest_problem)
    db.session.add(ContestParticipant(contest_id=contest.id, user_id=user.id))
    db.session.commit()
    return contest, contest_problem


def test_contest_password_is_hashed_and_admin_form_never_echoes_it(client, app):
    with app.app_context():
        admin = create_user('contest_hash_admin', 'contest_hash_admin@example.com', role='admin')
        problem = create_problem('Contest Password Problem')
        contest, _ = _contest(app, user=admin, problem=problem, password='secret-pass')
        contest_id = contest.id

        assert contest.password != 'secret-pass'
        assert check_password_hash(contest.password, 'secret-pass')
        contest.password = '   '
        assert contest.password is None

    _login(client, 'contest_hash_admin')
    response = client.get(f'/admin/contest/{contest_id}/edit')

    assert response.status_code == 200
    assert b'secret-pass' not in response.data
    assert b'type="password"' in response.data


def test_legacy_plaintext_contest_password_upgrades_after_successful_registration(client, app):
    with app.app_context():
        admin = create_user(
            'legacy_contest_admin', 'legacy_contest_admin@example.com', role='admin'
        )
        create_user('legacy_contest_student', 'legacy_contest_student@example.com')
        problem = create_problem('Legacy Contest Password Problem')
        contest, _ = _contest(app, user=admin, problem=problem, pending=True)
        contest.password = 'legacy-secret'
        db.session.commit()
        contest_id = contest.id

        # Simulate a pre-hardening database row without triggering the model setter.
        db.session.execute(
            db.text('UPDATE contest SET password = :password WHERE id = :contest_id'),
            {'password': 'legacy-secret', 'contest_id': contest_id},
        )
        db.session.commit()

    _login(client, 'legacy_contest_student')
    response = client.post(
        f'/contest/{contest_id}/register',
        data={'password': 'legacy-secret'},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        contest = db.session.get(Contest, contest_id)
        assert check_password_hash(contest.password, 'legacy-secret')
        assert (
            ContestParticipant.query.filter_by(
                contest_id=contest_id,
                user_id=db.session.execute(
                    db.text('SELECT id FROM user WHERE username = :username'),
                    {'username': 'legacy_contest_student'},
                ).scalar_one(),
            ).count()
            == 1
        )


def test_contest_submission_idempotency_key_deduplicates_retries(client, app, monkeypatch):
    with app.app_context():
        user = create_user('contest_retry_user', 'contest_retry_user@example.com')
        problem = create_problem('Contest Retry Problem')
        contest, contest_problem = _contest(app, user=user, problem=problem)
        contest_id = contest.id
        alias = contest_problem.alias
        user_id = user.id
        problem_id = problem.id

    _login(client, 'contest_retry_user')
    monkeypatch.setattr(app.judge_engine, 'submit_judge_task', lambda submission_id: True)
    payload = {
        'language': 'python',
        'code': 'print(1)',
        'idempotency_key': 'retry-token-001',
    }

    first = client.post(f'/contest/{contest_id}/submit/{alias}', data=payload)
    second = client.post(f'/contest/{contest_id}/submit/{alias}', data=payload)

    assert first.status_code == 302
    assert second.status_code == 302
    with app.app_context():
        submissions = Submission.query.filter_by(
            user_id=user_id, problem_id=problem_id, contest_id=contest_id
        ).all()
        assert len(submissions) == 1
        assert submissions[0].client_token == 'retry-token-001'


def test_ended_contest_problem_is_read_only_and_practice_is_explicit(client, app):
    with app.app_context():
        admin = create_user('ended_contest_admin', 'ended_contest_admin@example.com', role='admin')
        student = create_user('ended_contest_student', 'ended_contest_student@example.com')
        problem = create_problem('Ended Contest Problem')
        contest, contest_problem = _contest(app, user=admin, problem=problem, ended=True)
        db.session.add(ContestParticipant(contest_id=contest.id, user_id=student.id))
        db.session.commit()
        contest_id = contest.id
        alias = contest_problem.alias
        problem_id = problem.id
        student_id = student.id

    _login(client, 'ended_contest_student')
    response = client.get(f'/contest/{contest_id}/problem/{alias}')

    assert response.status_code == 200
    assert b'Ended Contest Problem' in response.data
    assert f'/problem/{problem_id}'.encode() in response.data
    assert f'/contest/{contest_id}/submit/{alias}'.encode() not in response.data
    assert f'/api/run/{problem_id}'.encode() not in response.data

    response = client.post(
        f'/contest/{contest_id}/submit/{alias}',
        data={'language': 'python', 'code': 'print(1)', 'idempotency_key': 'ended-token'},
    )
    assert response.status_code == 302
    with app.app_context():
        assert Submission.query.filter_by(contest_id=contest_id, user_id=student_id).count() == 0


def test_non_participant_cannot_read_or_submit_contest_problem(client, app):
    with app.app_context():
        admin = create_user(
            'boundary_contest_admin', 'boundary_contest_admin@example.com', role='admin'
        )
        create_user('boundary_contest_outsider', 'boundary_contest_outsider@example.com')
        problem = create_problem('Contest Boundary Problem')
        contest, contest_problem = _contest(app, user=admin, problem=problem)
        contest_id = contest.id
        alias = contest_problem.alias

    _login(client, 'boundary_contest_outsider')
    assert client.get(f'/contest/{contest_id}/problem/{alias}').status_code == 403
    assert (
        client.post(
            f'/contest/{contest_id}/submit/{alias}',
            data={'language': 'python', 'code': 'print(1)'},
        ).status_code
        == 403
    )
