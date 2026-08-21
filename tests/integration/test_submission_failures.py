import subprocess
import sys
from datetime import datetime
from datetime import timedelta
from pathlib import Path

from app import db
from app.models.contest import Contest
from app.models.contest_participant import ContestParticipant
from app.models.contest_problem import ContestProblem
from app.models.judge_task import JudgeTask
from app.models.submission import Submission
from tests.utils import create_problem
from tests.utils import create_user


def test_submission_service_import_has_no_judge_routes_cycle():
    repository = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            'import app.services.submission_service as service; '
            'assert service.QUEUE_UNAVAILABLE_MESSAGE',
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_queue_failure_marks_submission_failed_and_returns_identifier(client, app, monkeypatch):
    with app.app_context():
        user = create_user('queue_failure_user', 'queue-failure@example.com')
        username = user.username
        problem = create_problem('Queue Failure Problem')
        problem_id = problem.id

    client.post('/login', data={'username': username, 'password': 'password123'})
    monkeypatch.setattr(app.judge_engine, 'submit_judge_task', lambda submission_id: False)

    response = client.post(
        f'/api/submit/{problem_id}',
        json={'language': 'python', 'code': 'print(1)'},
    )

    assert response.status_code == 503
    submission_id = response.get_json()['data']['submission_id']
    with app.app_context():
        submission = db.session.get(Submission, submission_id)
        assert submission.status == 'Failed'
        assert 'queue' in submission.error_message.lower()


def test_oversized_api_submission_is_rejected_without_internal_error(client, app):
    with app.app_context():
        user = create_user('oversized_submitter', 'oversized-submitter@example.com')
        username = user.username
        problem = create_problem('Oversized Submission Problem')
        problem_id = problem.id

    client.post('/login', data={'username': username, 'password': 'password123'})
    response = client.post(
        f'/api/submit/{problem_id}',
        json={'language': 'python', 'code': 'x' * (app.config['MAX_CONTENT_LENGTH'] + 1)},
    )

    assert response.status_code in (400, 413)
    assert response.status_code != 500


def test_web_enqueue_exception_marks_submission_failed(client, app, monkeypatch):
    with app.app_context():
        user = create_user('web_queue_exception', 'web-queue-exception@example.com')
        problem = create_problem('Web Queue Exception Problem')
        username = user.username
        user_id = user.id
        problem_id = problem.id

    client.post('/login', data={'username': username, 'password': 'password123'})

    def raise_queue_error(submission_id):
        raise RuntimeError('simulated queue outage')

    monkeypatch.setattr(app.judge_engine, 'submit_judge_task', raise_queue_error)
    response = client.post(
        f'/problem/{problem_id}/submit',
        data={'language': 'python', 'code': 'print(3)'},
    )

    assert response.status_code == 302
    with app.app_context():
        submission = Submission.query.filter_by(user_id=user_id, problem_id=problem_id).one()
        assert submission.status == 'Failed'
        assert submission.error_message == 'Judge queue is full or unavailable.'


def test_contest_enqueue_exception_marks_submission_failed(client, app, monkeypatch):
    with app.app_context():
        admin = create_user('contest_queue_admin', 'contest-queue-admin@example.com', role='admin')
        user = create_user('contest_queue_user', 'contest-queue-user@example.com')
        problem = create_problem('Contest Queue Exception Problem')
        now = datetime.utcnow()
        contest = Contest(
            title='Contest Queue Exception',
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            is_public=True,
            created_by=admin.id,
        )
        db.session.add(contest)
        db.session.flush()
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

    client.post('/login', data={'username': 'contest_queue_user', 'password': 'password123'})

    def raise_queue_error(submission_id):
        raise RuntimeError('simulated queue outage')

    monkeypatch.setattr(app.judge_engine, 'submit_judge_task', raise_queue_error)
    response = client.post(
        f'/contest/{contest_id}/submit/A',
        data={'language': 'python', 'code': 'print(3)'},
    )

    assert response.status_code == 302
    with app.app_context():
        submission = Submission.query.filter_by(
            user_id=user_id,
            problem_id=problem_id,
            contest_id=contest_id,
        ).one()
        assert submission.status == 'Failed'
        assert submission.error_message == 'Judge queue is full or unavailable.'


def test_rejudge_enqueue_failure_never_leaves_pending_orphan(client, app, monkeypatch):
    with app.app_context():
        admin = create_user(
            'rejudge_failure_admin', 'rejudge-failure-admin@example.com', role='admin'
        )
        user = create_user('rejudge_failure_user', 'rejudge-failure-user@example.com')
        problem = create_problem('Rejudge Failure Problem')
        submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            language='python',
            code='print(1)',
            status='AC',
            submitted_at=datetime.utcnow(),
        )
        db.session.add(submission)
        db.session.flush()
        db.session.add(JudgeTask(submission_id=submission.id, status='Completed'))
        db.session.commit()
        submission_id = submission.id
        admin_username = admin.username

    client.post('/login', data={'username': admin_username, 'password': 'password123'})
    monkeypatch.setattr(app.judge_engine, 'submit_judge_task', lambda submission_id: False)

    response = client.post(f'/judge/rejudge/{submission_id}')

    assert response.status_code == 200
    assert response.get_json()['code'] == 503
    with app.app_context():
        refreshed = db.session.get(Submission, submission_id)
        assert refreshed.status == 'Failed'
        assert refreshed.error_message == 'Judge queue is full or unavailable.'
        retained_task = JudgeTask.query.filter_by(submission_id=submission_id).one()
        assert retained_task.status == 'Completed'
