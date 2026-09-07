"""A running contest must lock its problems for every account.

Registration closes once a contest starts, so a student who never joined could
otherwise reach the practice submit path and read expected output from the judge
report while the contest was still live.
"""

from datetime import datetime
from datetime import timedelta

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


def _running_contest(admin_id, title='Lockout Contest'):
    now = datetime.utcnow()
    contest = Contest(
        title=title,
        description='Test',
        start_time=now - timedelta(hours=1),
        end_time=now + timedelta(hours=1),
        is_public=True,
        created_by=admin_id,
    )
    db.session.add(contest)
    db.session.flush()
    return contest


def _attach(contest_id, problem_id, alias='A'):
    db.session.add(
        ContestProblem(
            contest_id=contest_id,
            problem_id=problem_id,
            alias=alias,
            display_order=1,
        )
    )
    db.session.commit()


def test_non_participant_cannot_practice_submit_problem_in_running_contest(client, app):
    with app.app_context():
        admin = create_user('lockout_admin', 'lockout_admin@example.com', role='admin')
        create_user('lockout_outsider', 'lockout_outsider@example.com')
        contest = _running_contest(admin.id)
        problem = create_problem('Locked Contest Problem')
        _attach(contest.id, problem.id)
        problem_id = problem.id

    _login(client, 'lockout_outsider')
    response = client.post(
        f'/problem/{problem_id}/submit',
        data={'language': 'python', 'code': 'print(0)'},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        assert Submission.query.filter_by(problem_id=problem_id).count() == 0


def test_non_participant_api_submit_is_rejected_while_contest_runs(client, app):
    with app.app_context():
        admin = create_user('api_lockout_admin', 'api_lockout_admin@example.com', role='admin')
        create_user('api_lockout_outsider', 'api_lockout_outsider@example.com')
        contest = _running_contest(admin.id, title='API Lockout Contest')
        problem = create_problem('API Locked Contest Problem')
        _attach(contest.id, problem.id)
        problem_id = problem.id

    _login(client, 'api_lockout_outsider')
    response = client.post(
        f'/api/submit/{problem_id}',
        json={'language': 'python', 'code': 'print(0)'},
    )

    assert response.status_code == 409
    with app.app_context():
        assert Submission.query.filter_by(problem_id=problem_id).count() == 0


def test_practice_submit_reopens_after_the_contest_ends(client, app):
    with app.app_context():
        admin = create_user('ended_admin', 'ended_admin@example.com', role='admin')
        create_user('ended_outsider', 'ended_outsider@example.com')
        now = datetime.utcnow()
        contest = Contest(
            title='Ended Lockout Contest',
            description='Test',
            start_time=now - timedelta(hours=3),
            end_time=now - timedelta(hours=1),
            is_public=True,
            created_by=admin.id,
        )
        db.session.add(contest)
        db.session.flush()
        problem = create_problem('Reopened Contest Problem')
        _attach(contest.id, problem.id)
        problem_id = problem.id

    _login(client, 'ended_outsider')
    response = client.get(f'/problem/{problem_id}/submit')

    assert response.status_code == 200


def test_participant_is_still_redirected_to_the_contest_page(client, app):
    with app.app_context():
        admin = create_user('redirect_admin', 'redirect_admin@example.com', role='admin')
        user = create_user('redirect_player', 'redirect_player@example.com')
        contest = _running_contest(admin.id, title='Redirect Contest')
        problem = create_problem('Redirect Contest Problem')
        _attach(contest.id, problem.id)
        db.session.add(ContestParticipant(contest_id=contest.id, user_id=user.id))
        db.session.commit()
        problem_id = problem.id
        contest_id = contest.id

    _login(client, 'redirect_player')
    response = client.get(f'/problem/{problem_id}/submit')

    assert response.status_code == 302
    assert f'/contest/{contest_id}/problem/A' in response.headers['Location']
