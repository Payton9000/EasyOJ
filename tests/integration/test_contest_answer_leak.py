import json
import time
from datetime import datetime
from datetime import timedelta
from pathlib import Path

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


def _make_running_contest(app, admin_user):
    now = datetime.utcnow()
    contest = Contest(
        title='Running Contest',
        description='Test',
        start_time=now - timedelta(hours=1),
        end_time=now + timedelta(hours=1),
        is_public=True,
        created_by=admin_user.id,
    )
    db.session.add(contest)
    db.session.flush()
    return contest


def _poll_submission(client, submission_id, timeout_s=10):
    deadline = time.time() + timeout_s
    data = None
    while time.time() < deadline:
        res = client.get(f'/api/submission/{submission_id}')
        data = res.get_json()
        status = data['data']['status']
        if status not in ('Pending', 'Queued', 'Judging'):
            return data['data']
        time.sleep(0.2)
    return data['data'] if data else None


def test_contest_running_hides_expected_output_in_diff(client, app):
    with app.app_context():
        admin = create_user('admin_diff', 'admin_diff@example.com', role='admin')
        user = create_user('student_diff', 'student_diff@example.com')

        contest = _make_running_contest(app, admin)

        problem = create_problem('Contest WA Test')
        problem.is_public = True
        db.session.commit()

        cp = ContestProblem(
            contest_id=contest.id,
            problem_id=problem.id,
            alias='A',
            display_order=1,
        )
        db.session.add(cp)

        participant = ContestParticipant(contest_id=contest.id, user_id=user.id)
        db.session.add(participant)
        db.session.commit()

        problem_id = problem.id
        contest_id = contest.id
        user_id = user.id
        write_testcases(app.config['BASE_DIR'], problem_id, [('1 2', '3')])

    _login(client, 'student_diff', 'password123')

    code_wa = 'print(0)'
    res = client.post(
        f'/contest/{contest_id}/submit/A',
        data={'language': 'python', 'code': code_wa},
        follow_redirects=True,
    )
    assert res.status_code == 200

    with app.app_context():
        submission = (
            Submission.query.filter_by(contest_id=contest_id, user_id=user_id)
            .order_by(Submission.id.desc())
            .first()
        )
        assert submission is not None
        submission_id = submission.id

    result = _poll_submission(client, submission_id, timeout_s=15)
    assert result is not None
    assert result['status'] == 'WA'

    detail = client.get(f'/submission/{submission_id}')
    assert detail.status_code == 200
    body = detail.data.decode('utf-8')
    assert 'Failed Case Diff' not in body
    assert 'Expected' not in body or 'expected' not in body.lower().replace('expected', '', 1)


def test_non_contest_submission_shows_expected_output_in_diff(client, app):
    with app.app_context():
        create_user('student_nodiff', 'student_nodiff@example.com')
        problem = create_problem('Non-Contest WA Test')
        problem_id = problem.id
        write_testcases(app.config['BASE_DIR'], problem_id, [('1 2', '3')])

    _login(client, 'student_nodiff', 'password123')

    code_wa = 'print(0)'
    res = client.post(
        f'/problem/{problem_id}/submit',
        data={'language': 'python', 'code': code_wa},
        follow_redirects=True,
    )
    assert res.status_code == 200

    with app.app_context():
        submission = (
            Submission.query.filter_by(problem_id=problem_id).order_by(Submission.id.desc()).first()
        )
        submission_id = submission.id

    result = _poll_submission(client, submission_id, timeout_s=15)
    assert result is not None
    assert result['status'] == 'WA'

    detail = client.get(f'/submission/{submission_id}')
    assert detail.status_code == 200
    body = detail.data.decode('utf-8')
    assert 'Failed Case Diff' in body


def test_legacy_unscoped_submission_hides_expected_output_during_contest(client, app):
    with app.app_context():
        admin = create_user('legacy_diff_admin', 'legacy_diff_admin@example.com', role='admin')
        user = create_user('legacy_diff_user', 'legacy_diff_user@example.com')
        contest = _make_running_contest(app, admin)
        contest.title = 'Legacy Isolation Contest'
        problem = create_problem('Legacy Contest Answer Problem')
        db.session.add(
            ContestProblem(
                contest_id=contest.id,
                problem_id=problem.id,
                alias='A',
                display_order=1,
            )
        )
        db.session.add(ContestParticipant(contest_id=contest.id, user_id=user.id))

        submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            contest_id=None,
            language='python',
            code='print(0)',
            status='WA',
        )
        db.session.add(submission)
        db.session.commit()

        log_dir = Path(app.config['JUDGE_LOG_DIR'])
        log_dir.mkdir(parents=True, exist_ok=True)
        log_payload = {
            'submission_id': submission.id,
            'final_status': 'WA',
            'cases': [
                {
                    'case': 1,
                    'status': 'WA',
                    'time_ms': 1,
                    'memory_kb': 1024,
                    'output_sample': 'wrong-output',
                    'expected_sample': 'secret-expected-answer',
                }
            ],
        }
        (log_dir / f'submission_{submission.id}.json').write_text(
            json.dumps(log_payload),
            encoding='utf-8',
        )
        submission_id = submission.id

    _login(client, 'legacy_diff_user', 'password123')
    response = client.get(f'/submission/{submission_id}')

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'secret-expected-answer' not in body
    assert 'Failed Case Diff' not in body
