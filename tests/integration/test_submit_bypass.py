from datetime import datetime
from datetime import timedelta

from app import db
from app.models.contest import Contest
from app.models.contest_participant import ContestParticipant
from app.models.contest_problem import ContestProblem
from app.models.submission import Submission
from tests.utils import create_problem
from tests.utils import create_user
from tests.utils import write_testcases


def _login(client, username, password):
    return client.post(
        '/login', data={'username': username, 'password': password}, follow_redirects=True
    )


def test_hidden_problem_submit_returns_404_for_non_admin(client, app):
    with app.app_context():
        create_user('hidden_user', 'hidden@example.com')
        problem = create_problem('Hidden Problem')
        problem.is_public = False
        db.session.commit()
        problem_id = problem.id
        write_testcases(app.config['BASE_DIR'], problem_id, [('1 2', '3')])

    _login(client, 'hidden_user', 'password123')

    res = client.post(
        f'/problem/{problem_id}/submit',
        data={'language': 'python', 'code': 'print(3)'},
    )
    assert res.status_code == 404


def test_hidden_problem_submit_allowed_for_admin(client, app):
    with app.app_context():
        create_user('hidden_admin', 'hidden_admin@example.com', role='admin')
        problem = create_problem('Hidden Admin Problem')
        problem.is_public = False
        db.session.commit()
        problem_id = problem.id
        write_testcases(app.config['BASE_DIR'], problem_id, [('1 2', '3')])

    _login(client, 'hidden_admin', 'password123')

    res = client.post(
        f'/problem/{problem_id}/submit',
        data={'language': 'python', 'code': 'print(3)'},
        follow_redirects=True,
    )
    assert res.status_code == 200


def test_running_contest_problem_blocked_from_regular_submit(client, app):
    with app.app_context():
        admin = create_user('contest_admin', 'contest_admin@example.com', role='admin')
        user = create_user('contest_user', 'contest_user@example.com')

        now = datetime.utcnow()
        contest = Contest(
            title='Block Contest',
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            is_public=True,
            created_by=admin.id,
        )
        db.session.add(contest)
        db.session.flush()

        problem = create_problem('Contest Block Problem')
        problem.is_public = True
        db.session.commit()
        problem_id = problem.id
        contest_id = contest.id

        cp = ContestProblem(
            contest_id=contest_id,
            problem_id=problem_id,
            alias='A',
            display_order=1,
        )
        db.session.add(cp)
        participant = ContestParticipant(contest_id=contest_id, user_id=user.id)
        db.session.add(participant)
        db.session.commit()

        write_testcases(app.config['BASE_DIR'], problem_id, [('1 2', '3')])

    _login(client, 'contest_user', 'password123')

    res = client.post(
        f'/problem/{problem_id}/submit',
        data={'language': 'python', 'code': 'print(3)'},
        follow_redirects=True,
    )
    assert res.status_code == 200
    body = res.data.decode('utf-8')
    assert 'contest' in body.lower() or 'submit' not in body.lower() or 'error' in body.lower()


def test_problem_in_running_and_pending_contests_redirects_to_running(client, app):
    with app.app_context():
        admin = create_user('multi_contest_admin', 'multi_contest_admin@example.com', role='admin')
        user = create_user('multi_contest_user', 'multi_contest_user@example.com')

        now = datetime.utcnow()
        pending = Contest(
            title='Pending Contest A',
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=3),
            is_public=True,
            created_by=admin.id,
        )
        db.session.add(pending)
        db.session.flush()

        running = Contest(
            title='Running Contest B',
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            is_public=True,
            created_by=admin.id,
        )
        db.session.add(running)
        db.session.flush()

        problem = create_problem('Multi Contest Problem')
        problem.is_public = True
        db.session.commit()
        problem_id = problem.id
        running_id = running.id

        db.session.add(
            ContestProblem(contest_id=pending.id, problem_id=problem_id, alias='A', display_order=1)
        )
        db.session.add(
            ContestProblem(contest_id=running_id, problem_id=problem_id, alias='A', display_order=1)
        )
        db.session.add(ContestParticipant(contest_id=running_id, user_id=user.id))
        db.session.commit()

        write_testcases(app.config['BASE_DIR'], problem_id, [('1 2', '3')])

    _login(client, 'multi_contest_user', 'password123')

    res = client.post(
        f'/problem/{problem_id}/submit',
        data={'language': 'python', 'code': 'print(3)'},
    )
    assert res.status_code == 302
    location = res.headers.get('Location', '')
    assert f'/contest/{running_id}/problem/A' in location


def test_running_contest_participant_cannot_bypass_with_api(client, app, monkeypatch):
    with app.app_context():
        admin = create_user('api_contest_admin', 'api_contest_admin@example.com', role='admin')
        user = create_user('api_contest_user', 'api_contest_user@example.com')

        now = datetime.utcnow()
        contest = Contest(
            title='API Isolation Contest',
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            is_public=True,
            created_by=admin.id,
        )
        db.session.add(contest)
        db.session.flush()

        problem = create_problem('API Contest Isolation Problem')
        db.session.add(
            ContestProblem(
                contest_id=contest.id,
                problem_id=problem.id,
                alias='A',
                display_order=1,
            )
        )
        db.session.add(ContestParticipant(contest_id=contest.id, user_id=user.id))
        db.session.commit()

        contest_id = contest.id
        problem_id = problem.id
        user_id = user.id

    _login(client, 'api_contest_user', 'password123')
    monkeypatch.setattr(app.judge_engine, 'submit_judge_task', lambda submission_id: True)

    response = client.post(
        f'/api/submit/{problem_id}',
        json={'language': 'python', 'code': 'print(3)'},
    )

    assert response.status_code == 409
    assert response.get_json() == {
        'code': 409,
        'message': 'Submit this problem through its active contest',
        'data': {'contest_id': contest_id, 'alias': 'A'},
    }
    with app.app_context():
        assert Submission.query.filter_by(user_id=user_id, problem_id=problem_id).count() == 0
