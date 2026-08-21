import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Event

from app import db
from app.judge.admission import check_submission_admission
from app.models.judge_task import JudgeTask
from app.models.submission import Submission
from app.services.submission_service import enqueue_submission
from tests.utils import create_problem
from tests.utils import create_user


def _queued_submission(user_id, problem_id):
    submission = Submission(
        user_id=user_id,
        problem_id=problem_id,
        language='python',
        code='print(1)',
        status='Queued',
        submitted_at=datetime.utcnow(),
    )
    db.session.add(submission)
    db.session.flush()
    db.session.add(JudgeTask(submission_id=submission.id, status='Queued'))
    db.session.commit()
    return submission


def test_admission_rejects_user_at_active_submission_limit(app):
    with app.app_context():
        app.config['JUDGE_TOTAL_ACTIVE_MAX'] = 100
        app.config['JUDGE_USER_ACTIVE_MAX'] = 1
        user = create_user('admission_user_limit', 'admission_user_limit@example.com')
        problem = create_problem('Admission User Limit')
        _queued_submission(user.id, problem.id)

        decision = check_submission_admission(user.id)

        assert decision.accepted is False
        assert decision.reason == 'user active submission limit reached'
        assert decision.retry_after == 30


def test_admission_rejects_system_at_active_submission_limit(app):
    with app.app_context():
        app.config['JUDGE_TOTAL_ACTIVE_MAX'] = 1
        app.config['JUDGE_USER_ACTIVE_MAX'] = 100
        user_a = create_user('admission_system_a', 'admission_system_a@example.com')
        user_b = create_user('admission_system_b', 'admission_system_b@example.com')
        problem = create_problem('Admission System Limit')
        _queued_submission(user_a.id, problem.id)

        decision = check_submission_admission(user_b.id)

        assert decision.accepted is False
        assert decision.reason == 'system active submission limit reached'
        assert decision.retry_after == 15


def test_admission_ignores_terminal_tasks(app):
    with app.app_context():
        app.config['JUDGE_TOTAL_ACTIVE_MAX'] = 100
        app.config['JUDGE_USER_ACTIVE_MAX'] = 1
        user = create_user('admission_terminal', 'admission_terminal@example.com')
        problem = create_problem('Admission Terminal')
        submission = _queued_submission(user.id, problem.id)
        submission.status = 'AC'
        JudgeTask.query.filter_by(submission_id=submission.id).update({'status': 'Completed'})
        db.session.commit()

        decision = check_submission_admission(user.id)

        assert decision.accepted is True
        assert decision.reason == ''


def test_enqueue_admission_is_atomic_for_concurrent_same_user_submissions(app, monkeypatch):
    """A slow queue handoff must not let two requests reserve one user slot."""
    with app.app_context():
        app.config['JUDGE_TOTAL_ACTIVE_MAX'] = 100
        app.config['JUDGE_USER_ACTIVE_MAX'] = 1
        user = create_user('admission_race_user', 'admission_race@example.com')
        problem = create_problem('Admission Race')
        submissions = []
        for index in range(2):
            submission = Submission(
                user_id=user.id,
                problem_id=problem.id,
                language='python',
                code=f'print({index})',
                status='Pending',
            )
            db.session.add(submission)
            submissions.append(submission)
        db.session.commit()
        submission_ids = [submission.id for submission in submissions]
        user_id = user.id

    first_handoff_started = Event()
    release_first_handoff = Event()
    call_count = 0

    def slow_handoff(submission_id):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            first_handoff_started.set()
            release_first_handoff.wait(timeout=2)
        with app.app_context():
            submission = db.session.get(Submission, submission_id)
            db.session.add(JudgeTask(submission_id=submission_id, status='Queued'))
            submission.status = 'Queued'
            db.session.commit()
        return True

    monkeypatch.setattr(app.judge_engine, 'submit_judge_task', slow_handoff)

    def enqueue_in_context(submission_id):
        with app.app_context():
            try:
                return enqueue_submission(db.session.get(Submission, submission_id))
            finally:
                db.session.remove()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(enqueue_in_context, submission_ids[0])
        assert first_handoff_started.wait(timeout=2)
        second = pool.submit(enqueue_in_context, submission_ids[1])
        time.sleep(0.05)
        release_first_handoff.set()
        results = [first.result(timeout=3), second.result(timeout=3)]

    with app.app_context():
        active = (
            JudgeTask.query.join(Submission)
            .filter(
                JudgeTask.status == 'Queued',
                Submission.user_id == user_id,
            )
            .count()
        )

    assert sorted(results) == [False, True]
    assert active == 1
