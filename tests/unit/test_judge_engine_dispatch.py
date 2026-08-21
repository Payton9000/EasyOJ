import queue
from datetime import datetime
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app import create_app
from app import db
from app.models.judge_task import JudgeTask
from app.models.submission import Submission
from tests.utils import create_problem
from tests.utils import create_user


def _build_isolated_app(tmp_path):
    base_dir = tmp_path / 'base'
    (base_dir / 'data').mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / 'judge_flow.db'

    app = create_app(
        'testing',
        start_judge_engine=False,
        config_overrides={
            'BASE_DIR': str(base_dir),
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'JUDGE_QUEUE_MAXSIZE': 10,
        },
    )

    with app.app_context():
        db.drop_all()
        db.create_all()

    app.judge_engine.is_running = True
    app.judge_engine.workers = [SimpleNamespace(name='JudgeWorker-test', is_alive=lambda: True)]
    return app


def test_submit_and_dispatch_follow_single_enqueue_path(tmp_path):
    app = _build_isolated_app(tmp_path)

    with app.app_context():
        user = create_user('dispatch_user', 'dispatch_user@example.com')
        problem = create_problem('Dispatch Problem')
        submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            language='python',
            code='print(1)',
            status='Pending',
            submitted_at=datetime.utcnow(),
        )
        db.session.add(submission)
        db.session.commit()
        submission_id = submission.id

        assert app.judge_engine.submit_judge_task(submission_id) is True
        db.session.expire_all()

        task = JudgeTask.query.filter_by(submission_id=submission_id).first()
        assert task is not None
        assert task.status == 'Queued'
        assert db.session.get(Submission, submission_id).status == 'Queued'

        app.judge_engine._dispatch_queued_tasks(limit=5)
        db.session.expire_all()
        dispatched_task = JudgeTask.query.filter_by(submission_id=submission_id).first()
        assert dispatched_task.status == 'Dispatched'

        # Re-running dispatcher should not enqueue the same queued task twice.
        app.judge_engine._dispatch_queued_tasks(limit=5)

    # multiprocessing.Queue publishes through a feeder thread, so an item
    # accepted by put_nowait() may not be immediately visible to get_nowait().
    first_item = app.judge_engine.task_queue.get(timeout=1)
    assert first_item == submission_id
    app.judge_engine.task_queue.task_done()

    with pytest.raises(queue.Empty):
        app.judge_engine.task_queue.get(timeout=0.1)


class _Guard:
    def __init__(self, allowed, reason=''):
        self.allowed = allowed
        self.reason = reason
        self.latest_snapshot = None

    def can_dispatch(self):
        return self.allowed, self.reason


def test_dispatch_pauses_under_host_pressure_and_recovers_once(tmp_path):
    app = _build_isolated_app(tmp_path)

    with app.app_context():
        user = create_user('pressure_user', 'pressure_user@example.com')
        problem = create_problem('Pressure Problem')
        submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            language='python',
            code='print(1)',
            status='Pending',
            submitted_at=datetime.utcnow(),
        )
        db.session.add(submission)
        db.session.commit()
        submission_id = submission.id

        assert app.judge_engine.submit_judge_task(submission_id) is True
        app.judge_engine.host_guard = _Guard(False, 'host CPU usage is high')
        app.judge_engine._dispatch_queued_tasks(limit=5)

        task = JudgeTask.query.filter_by(submission_id=submission_id).first()
        assert task.status == 'Queued'
        assert app.judge_engine.dispatch_pause_reason == 'host CPU usage is high'

        app.judge_engine.host_guard = _Guard(True)
        app.judge_engine._dispatch_queued_tasks(limit=5)
        db.session.expire_all()
        assert JudgeTask.query.filter_by(submission_id=submission_id).first().status == 'Dispatched'
        assert app.judge_engine.dispatch_pause_reason == ''

    queued_submission_id = app.judge_engine.task_queue.get(timeout=1)
    assert queued_submission_id == submission_id
    app.judge_engine.task_queue.task_done()
    with pytest.raises(queue.Empty):
        app.judge_engine.task_queue.get(timeout=0.1)


def test_submit_rejects_when_engine_is_stopped(tmp_path):
    app = _build_isolated_app(tmp_path)
    app.judge_engine.is_running = False

    with app.app_context():
        user = create_user('stopped_engine_user', 'stopped-engine@example.com')
        problem = create_problem('Stopped Engine Problem')
        submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            language='python',
            code='print(1)',
            status='Pending',
            submitted_at=datetime.utcnow(),
        )
        db.session.add(submission)
        db.session.commit()

        assert app.judge_engine.is_running is False
        assert app.judge_engine.submit_judge_task(submission.id) is False
        assert JudgeTask.query.filter_by(submission_id=submission.id).first() is None


def test_submit_rejects_when_engine_has_no_live_workers(tmp_path):
    app = _build_isolated_app(tmp_path)
    engine = app.judge_engine
    engine.is_running = True
    engine.workers = []

    with app.app_context():
        user = create_user('dead_worker_submitter', 'dead-worker@example.com')
        problem = create_problem('Dead Worker Problem')
        submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            language='python',
            code='print(1)',
            status='Pending',
            submitted_at=datetime.utcnow(),
        )
        db.session.add(submission)
        db.session.commit()

        assert engine.submit_judge_task(submission.id) is False
        assert JudgeTask.query.filter_by(submission_id=submission.id).first() is None


def test_startup_reconciles_interrupted_tasks_and_orphaned_judging_submission(tmp_path):
    app = _build_isolated_app(tmp_path)
    engine = app.judge_engine

    with app.app_context():
        user = create_user('recovery_user', 'recovery@example.com')
        problem = create_problem('Recovery Problem')
        running_submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            language='python',
            code='print(1)',
            status='Judging',
            submitted_at=datetime.utcnow(),
        )
        orphaned_submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            language='python',
            code='print(2)',
            status='Judging',
            submitted_at=datetime.utcnow(),
        )
        db.session.add_all([running_submission, orphaned_submission])
        db.session.flush()
        db.session.add(
            JudgeTask(
                submission_id=running_submission.id,
                status='Running',
                worker_id='JudgeWorker-previous',
                started_at=datetime.utcnow(),
                last_heartbeat_at=datetime.utcnow(),
            )
        )
        db.session.commit()

        engine._reconcile_persisted_tasks()
        db.session.expire_all()

        recovered_task = JudgeTask.query.filter_by(submission_id=running_submission.id).one()
        assert recovered_task.status == 'Queued'
        assert recovered_task.worker_id is None
        assert db.session.get(Submission, running_submission.id).status == 'Queued'
        assert db.session.get(Submission, orphaned_submission.id).status == 'Failed'


def test_watchdog_fails_stale_queued_task(tmp_path):
    app = _build_isolated_app(tmp_path)
    engine = app.judge_engine
    engine.queued_task_timeout_ms = 1

    with app.app_context():
        user = create_user('stale_queue_user', 'stale-queue@example.com')
        problem = create_problem('Stale Queue Problem')
        submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            language='python',
            code='print(1)',
            status='Queued',
            submitted_at=datetime.utcnow(),
        )
        db.session.add(submission)
        db.session.flush()
        db.session.add(
            JudgeTask(
                submission_id=submission.id,
                status='Queued',
                created_at=datetime.utcnow() - timedelta(seconds=1),
                last_heartbeat_at=datetime.utcnow() - timedelta(seconds=1),
            )
        )
        db.session.commit()

        engine._cleanup_stale_tasks()
        db.session.expire_all()
        task = JudgeTask.query.filter_by(submission_id=submission.id).one()
        assert task.status == 'Failed'
        assert db.session.get(Submission, submission.id).status == 'Failed'
        assert 'queue' in (task.last_error or '').lower()


def test_watchdog_requeues_task_owned_by_dead_worker(tmp_path):
    app = _build_isolated_app(tmp_path)
    engine = app.judge_engine
    engine.is_running = True
    engine.workers = []

    with app.app_context():
        user = create_user('lost_worker_user', 'lost-worker@example.com')
        problem = create_problem('Lost Worker Problem')
        submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            language='python',
            code='print(1)',
            status='Judging',
            submitted_at=datetime.utcnow(),
        )
        db.session.add(submission)
        db.session.flush()
        db.session.add(
            JudgeTask(
                submission_id=submission.id,
                status='Running',
                worker_id='JudgeWorker-dead',
                started_at=datetime.utcnow(),
                last_heartbeat_at=datetime.utcnow(),
            )
        )
        db.session.commit()

        engine._reconcile_dead_workers()
        db.session.expire_all()
        task = JudgeTask.query.filter_by(submission_id=submission.id).one()
        assert task.status == 'Queued'
        assert task.worker_id is None
        assert db.session.get(Submission, submission.id).status == 'Queued'
