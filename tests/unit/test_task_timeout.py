from datetime import datetime
from datetime import timedelta

from app import db
from app.models.judge_task import JudgeTask
from app.models.submission import Submission
from tests.utils import create_problem
from tests.utils import create_user
from tests.utils import write_testcases


def test_cleanup_does_not_requeue_running_task_within_dynamic_timeout(app):
    with app.app_context():
        user = create_user('dyn_timeout', 'dyn_timeout@example.com')
        problem = create_problem('Dynamic Timeout Problem')
        problem.time_limit = 10000  # 10s per case
        db.session.commit()
        problem_id = problem.id
        write_testcases(app.config['BASE_DIR'], problem_id, [('1', '2')] * 10)

        submission = Submission(
            user_id=user.id,
            problem_id=problem_id,
            language='python',
            code='print(2)',
            status='Judging',
        )
        db.session.add(submission)
        db.session.flush()

        heartbeat = datetime.utcnow() - timedelta(seconds=200)

        task = JudgeTask(
            submission_id=submission.id,
            status='Running',
            started_at=heartbeat,
            last_heartbeat_at=heartbeat,
            worker_id='test-worker',
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

        engine = app.judge_engine
        engine._cleanup_stale_tasks()

        refreshed = db.session.get(JudgeTask, task_id)
        assert refreshed.status == 'Running', (
            f'Expected Running but got {refreshed.status} - '
            f'task should not be requeued within dynamic timeout '
            f'(10s * 10 cases = 100s + overhead > 200s heartbeat gap)'
        )


def test_cleanup_requeues_dispatched_task_past_fixed_timeout(app):
    with app.app_context():
        user = create_user('dispatch_timeout', 'dispatch_timeout@example.com')
        problem = create_problem('Dispatch Problem')
        problem_id = problem.id
        write_testcases(app.config['BASE_DIR'], problem_id, [('1', '2')])

        submission = Submission(
            user_id=user.id,
            problem_id=problem_id,
            language='python',
            code='print(2)',
            status='Queued',
        )
        db.session.add(submission)
        db.session.flush()

        old_time = datetime.utcnow() - timedelta(seconds=300)

        task = JudgeTask(
            submission_id=submission.id,
            status='Dispatched',
            started_at=None,
            last_heartbeat_at=old_time,
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

        engine = app.judge_engine
        engine._cleanup_stale_tasks()

        refreshed = db.session.get(JudgeTask, task_id)
        assert refreshed.status == 'Queued'


def test_dynamic_task_timeout_cached_between_calls(app, monkeypatch):
    from app.judge.engine import JudgeEngine
    from app.utils import file_utils

    calls = []
    original = file_utils.count_test_cases

    def counting(problem_id):
        calls.append(problem_id)
        return original(problem_id)

    engine = JudgeEngine(app, 'testing')
    with app.app_context():
        user = create_user('cache_user', 'cache@example.com')
        problem = create_problem('Cache Problem')
        problem.time_limit = 10000
        db.session.commit()
        problem_id = problem.id
        write_testcases(app.config['BASE_DIR'], problem_id, [('1', '2')] * 3)

        submission = Submission(
            user_id=user.id,
            problem_id=problem_id,
            language='python',
            code='print(2)',
            status='Running',
        )
        db.session.add(submission)
        db.session.flush()

        task = JudgeTask(
            submission_id=submission.id,
            status='Running',
            started_at=datetime.utcnow(),
            last_heartbeat_at=datetime.utcnow(),
            worker_id='test-worker',
        )
        db.session.add(task)
        db.session.commit()

        monkeypatch.setattr(file_utils, 'count_test_cases', counting)

        first = engine._dynamic_task_timeout(task)
        second = engine._dynamic_task_timeout(task)

        assert first == second
        assert calls == [problem_id]
