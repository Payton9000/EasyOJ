import json
import logging
import multiprocessing
import os
import queue
import threading
import time
from datetime import datetime
from datetime import timedelta

from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

HEARTBEAT_MIN_INTERVAL_SECONDS = 0.5

TASK_RECOVERY_MESSAGE = 'Judge task recovered after worker restart.'
STALE_QUEUE_MESSAGE = 'Judge task remained queued beyond the watchdog limit.'
WORKER_LOST_MESSAGE = 'Judge worker exited before completing the task.'


class _JudgeExecutionService:
    def __init__(self, app, max_retries, log_dir):
        self.app = app
        self.max_retries = max_retries
        self.log_dir = log_dir
        if self.log_dir:
            os.makedirs(self.log_dir, exist_ok=True)

    def execute_judge(self, submission, task) -> dict:
        from app import db
        from app.judge.comparator import Comparator
        from app.judge.compiler import Compiler
        from app.judge.executor import Executor
        from app.utils.file_utils import cleanup_dir
        from app.utils.file_utils import create_judge_workspace
        from app.utils.file_utils import iter_testcase_files
        from app.utils.file_utils import read_test_case
        from app.utils.file_utils import write_code_file

        work_dir = None
        case_logs = []
        try:
            work_dir = create_judge_workspace(submission.id)
            source_path = write_code_file(work_dir, submission.code, submission.language)

            compiler = Compiler(self.app)
            executor = Executor(self.app)
            comparator = Comparator()
            cfg = self.app.config

            # Scan the testcase directory once: a second, independent scan used to
            # decide `total` while the loop iterated a different snapshot, which
            # could report AC after running fewer cases than were counted.
            cases = list(iter_testcase_files(submission.problem_id))
            total = len(cases)
            if not total:
                return {
                    'status': 'Failed',
                    'error_message': 'No test cases',
                    'passed': 0,
                    'total': 0,
                }

            if submission.language in ('cpp', 'java'):
                compile_result = compiler.compile(source_path, submission.language, work_dir)
                if not compile_result['success']:
                    return {
                        'status': 'CE',
                        'error_message': compile_result['error'],
                        'passed': 0,
                        'total': 0,
                    }

            problem = submission.problem
            default_time = cfg.get('JUDGE_TIMEOUT', 30000)
            max_time = cfg.get('MAX_TIME_LIMIT_MS', default_time)
            time_limit = problem.time_limit if problem else default_time
            time_limit = min(time_limit, max_time)

            default_memory = 256
            max_memory = cfg.get('MAX_MEMORY_LIMIT_MB', 512)
            memory_limit = problem.memory_limit if problem else default_memory
            memory_limit = min(memory_limit, max_memory)

            max_time_used = 0
            max_memory_used = 0
            passed = 0
            last_heartbeat = 0.0
            for i, case in enumerate(cases, 1):
                input_data, expected_output = read_test_case(case)
                exec_result = executor.execute(
                    work_dir, submission.language, input_data, time_limit, memory_limit
                )
                status = exec_result.get('status', 'RE')
                case_log = {
                    'case': i,
                    'status': status,
                    'time_ms': exec_result.get('time_used', 0),
                    'memory_kb': exec_result.get('memory_used', 0),
                    'error': exec_result.get('error', ''),
                    'output_sample': exec_result.get('output', '')[:512],
                }
                case_logs.append(case_log)

                # Throttle the heartbeat write: one commit per case contends for the
                # single SQLite writer with every worker and the dispatcher, and the
                # watchdog timeout is far coarser than a per-case interval.
                now = time.monotonic()
                if now - last_heartbeat >= HEARTBEAT_MIN_INTERVAL_SECONDS or i == total:
                    task.last_heartbeat_at = datetime.utcnow()
                    db.session.commit()
                    last_heartbeat = now

                if status != 'OK':
                    self.write_judge_log(submission.id, case_logs, status)
                    return {
                        'status': status,
                        'error_message': exec_result.get('error', ''),
                        'time_used': exec_result.get('time_used', 0),
                        'memory_used': exec_result.get('memory_used', 0),
                        'passed': passed,
                        'total': total,
                    }

                if not comparator.compare(exec_result.get('output', ''), expected_output):
                    case_log['status'] = 'WA'
                    case_log['expected_sample'] = expected_output[:512]
                    self.write_judge_log(submission.id, case_logs, 'WA')
                    return {
                        'status': 'WA',
                        'error_message': f'Wrong answer on test case {i}',
                        'time_used': exec_result.get('time_used', 0),
                        'memory_used': exec_result.get('memory_used', 0),
                        'passed': passed,
                        'total': total,
                    }

                passed += 1
                max_time_used = max(max_time_used, exec_result.get('time_used', 0))
                max_memory_used = max(max_memory_used, exec_result.get('memory_used', 0))

            self.write_judge_log(submission.id, case_logs, 'AC')
            return {
                'status': 'AC',
                'time_used': max_time_used,
                'memory_used': max_memory_used,
                'passed': passed,
                'total': total,
            }
        except Exception as e:
            self.write_judge_log(submission.id, case_logs, 'SystemError', str(e))
            return {'status': 'SystemError', 'error_message': str(e), 'passed': 0, 'total': 0}
        finally:
            if work_dir:
                cleanup_dir(work_dir)

    def should_retry(self, status, error_message=''):
        if status == 'SystemError':
            return True
        return status == 'Failed' and error_message not in {'No test cases'}

    def handle_task_failure(self, task, submission, error_message, retryable=False):
        from app import db

        task.last_error = (error_message or '')[:1000]
        if retryable and task.retry_count < self.max_retries:
            task.retry_count += 1
            task.status = 'Queued'
            task.worker_id = None
            task.last_heartbeat_at = datetime.utcnow()
            task.completed_at = None
            if submission:
                # The failed attempt already wrote its metrics onto the submission.
                # Leaving them behind showed "Queued" alongside a judged-at stamp
                # and a passed count from the run that just failed.
                submission.status = 'Queued'
                submission.time_used = None
                submission.memory_used = None
                submission.test_case_passed = 0
                submission.test_case_total = 0
                submission.judged_at = None
                submission.error_message = None
            db.session.commit()
            logger.warning(
                'Re-queued submission_id=%s (attempt %s)',
                task.submission_id,
                task.retry_count,
            )
            return True

        task.status = 'Failed'
        task.completed_at = datetime.utcnow()
        if submission:
            submission.status = 'Failed'
        db.session.commit()
        return False

    def write_judge_log(self, submission_id, case_logs, final_status, error_message=None):
        if not self.log_dir:
            return None

        payload = {
            'submission_id': submission_id,
            'final_status': final_status,
            'error': error_message or '',
            'cases': case_logs,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
        }
        log_path = os.path.join(self.log_dir, f'submission_{submission_id}.json')
        try:
            with open(log_path, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle, ensure_ascii=True, indent=2)

            from app import db
            from app.models.judge_task import JudgeTask

            task = JudgeTask.query.filter_by(submission_id=submission_id).first()
            if task:
                task.debug_log_path = log_path
                db.session.commit()
            return log_path
        except Exception as e:
            logger.error('Failed to write judge log: %s', e)
            return None


class JudgeEngine:
    def __init__(self, app, config_name='default'):
        from app.judge.host_guard import HostCapacityGuard
        from app.judge.policy import JudgePolicy

        self.app = app
        self.config_name = config_name
        self.policy = JudgePolicy.from_config(app.config)

        # Capture relevant config for workers
        self.worker_config = {
            'SQLALCHEMY_DATABASE_URI': app.config.get('SQLALCHEMY_DATABASE_URI'),
            'BASE_DIR': app.config.get('BASE_DIR'),
            'SANDBOX_ENABLED': app.config.get('SANDBOX_ENABLED', True),
            'JUDGE_REQUIRE_SANDBOX': app.config.get('JUDGE_REQUIRE_SANDBOX', True),
            'SANDBOX_APP_CONTAINER': app.config.get('SANDBOX_APP_CONTAINER', True),
            'SANDBOX_STRICT_APP_CONTAINER': app.config.get('SANDBOX_STRICT_APP_CONTAINER', True),
            'SANDBOX_PROFILE_NAME': app.config.get('SANDBOX_PROFILE_NAME', 'EasyOJ.Sandbox'),
            'SANDBOX_MAX_PROCESSES': self.policy.max_processes,
            'SANDBOX_MAX_WORKSPACE_BYTES': self.policy.max_workspace_bytes,
            'SANDBOX_MAX_WORKSPACE_FILES': self.policy.max_workspace_files,
            'MAX_OUTPUT_SIZE': self.policy.max_output_size,
            'MAX_TIME_LIMIT_MS': self.policy.max_time_limit_ms,
            'MAX_MEMORY_LIMIT_MB': self.policy.max_memory_limit_mb,
            'JUDGE_COMPILE_TIMEOUT_MS': min(
                max(1, int(app.config.get('JUDGE_COMPILE_TIMEOUT_MS', 30000))),
                self.policy.max_time_limit_ms,
            ),
            'JUDGE_COMPILE_MEMORY_MB': min(
                max(1, int(app.config.get('JUDGE_COMPILE_MEMORY_MB', 512))),
                self.policy.max_memory_limit_mb,
            ),
            'JUDGE_TIMEOUT': app.config.get('JUDGE_TIMEOUT', 30000),
            'COMPILER_PATHS': app.config.get('COMPILER_PATHS', {}),
            'SUPPORTED_LANGUAGES': app.config.get('SUPPORTED_LANGUAGES', {}),
        }

        queue_size = self.policy.queue_maxsize
        self.mp_ctx = multiprocessing.get_context('spawn')
        self.task_queue = self.mp_ctx.JoinableQueue(maxsize=queue_size)
        self.workers = []
        self.worker_processes = []
        self.max_workers = self.policy.max_workers
        self.task_timeout_ms = max(1, int(app.config.get('JUDGE_TASK_TIMEOUT_MS', 180000)))
        configured_queue_timeout = int(
            app.config.get('JUDGE_QUEUED_TIMEOUT_MS', self.task_timeout_ms * 2)
        )
        self.queued_task_timeout_ms = min(max(1000, configured_queue_timeout), 86400000)
        self.max_retries = app.config.get('JUDGE_TASK_MAX_RETRIES', 2)
        # Backoff applies only when the host guard refuses dispatch. Idle polling is
        # a separate, shorter safety net because new work signals the dispatcher
        # directly; without the split every submission waited a full backoff period.
        self.host_backoff_seconds = min(
            max(0.1, int(app.config.get('JUDGE_HOST_BACKOFF_MS', 1000)) / 1000.0),
            10.0,
        )
        self.dispatch_poll_seconds = min(
            max(0.05, int(app.config.get('JUDGE_DISPATCH_POLL_MS', 500)) / 1000.0),
            10.0,
        )
        # Retained for callers/tests that inspect the legacy attribute name.
        self.dispatch_interval_seconds = self.host_backoff_seconds
        self.log_dir = app.config.get('JUDGE_LOG_DIR')
        self.is_running = False
        self.stop_event = self.mp_ctx.Event()
        self.execution_service = _JudgeExecutionService(app, self.max_retries, self.log_dir)
        self._task_timeout_cache = {}
        self.host_guard = HostCapacityGuard(
            app.config.get('JUDGE_HOST_MAX_CPU_PERCENT', 100),
            app.config.get('JUDGE_HOST_MIN_AVAILABLE_MEMORY_MB', 1024),
            reserved_memory_budget_mb=app.config.get('JUDGE_RESERVED_MEMORY_BUDGET_MB'),
            reserved_process_budget=app.config.get('JUDGE_RESERVED_PROCESS_BUDGET'),
        )
        self.dispatch_pause_reason = ''
        self._state_lock = threading.RLock()
        self._last_worker_restart_at = None
        self._task_reservations = {}
        # Set by submit_judge_task so a fresh submission does not wait for the
        # next poll tick before the dispatcher looks at the queue.
        self._wakeup_event = threading.Event()

        if self.log_dir:
            os.makedirs(self.log_dir, exist_ok=True)

    def start(self):
        with self._state_lock:
            if self.is_running or any(self._worker_is_alive(worker) for worker in self.workers):
                logger.warning('JudgeEngine start ignored because workers are already running')
                return False

            try:
                with self.app.app_context():
                    self._reconcile_persisted_tasks()
            except Exception:
                logger.exception('JudgeEngine startup reconciliation failed')
                return False

            self.workers.clear()
            self.worker_processes.clear()
            self.stop_event.clear()
            for i in range(self.max_workers):
                worker = self._spawn_worker(i)
                if worker is not None:
                    self.worker_processes.append(worker)
                    self.workers.append(worker)

            if not self.worker_processes:
                self.stop_event.set()
                self.is_running = False
                logger.error('JudgeEngine could not start any worker')
                return False
            self.is_running = True

            dispatcher = threading.Thread(
                target=self._dispatcher_loop,
                name='JudgeDispatcher',
                daemon=True,
            )
            dispatcher.start()
            self.workers.append(dispatcher)
        logger.info('JudgeEngine started with %d workers', self.max_workers)
        return True

    def stop(self):
        with self._state_lock:
            if not self.is_running and not self.workers:
                return True
            self.is_running = False
            self.stop_event.set()
            self._wakeup_event.set()
            for _ in range(max(1, len(self.worker_processes))):
                try:
                    self.task_queue.put_nowait(None)
                except queue.Full:
                    break
            survivors = []
            for worker in self.workers:
                worker.join(timeout=5)
                if self._worker_is_alive(worker):
                    survivors.append(worker)
            self.workers = survivors
            self.worker_processes = [
                worker for worker in self.worker_processes if self._worker_is_alive(worker)
            ]
            for reservation in self._task_reservations.values():
                self.host_guard.release(reservation)
            self._task_reservations.clear()
        if survivors:
            logger.warning('JudgeEngine stopped with %d worker(s) still alive', len(survivors))
        else:
            logger.info('JudgeEngine stopped')
        return not survivors

    @staticmethod
    def _worker_is_alive(worker):
        try:
            return bool(worker.is_alive())
        except Exception:
            return False

    def _live_worker_processes(self):
        processes = self.worker_processes or [
            worker for worker in self.workers if not isinstance(worker, threading.Thread)
        ]
        return [worker for worker in processes if self._worker_is_alive(worker)]

    def _live_worker_count(self):
        return len(self._live_worker_processes())

    def _spawn_worker(self, index):
        try:
            worker = self.mp_ctx.Process(
                target=_worker_process,
                name=f'JudgeWorker-{index}',
                args=(
                    self.config_name,
                    self.task_queue,
                    self.stop_event,
                    self.max_retries,
                    self.log_dir,
                    self.worker_config,
                ),
                daemon=True,
            )
            worker.start()
            self._last_worker_restart_at = datetime.utcnow()
            return worker
        except Exception:
            logger.exception('Failed to start judge worker %s', index)
            return None

    def _reconcile_persisted_tasks(self):
        """Make tasks from a previous process safe to dispatch after restart."""
        from app import db
        from app.models.judge_task import JudgeTask
        from app.models.submission import Submission

        active_tasks = JudgeTask.query.filter(
            JudgeTask.status.in_(['Queued', 'Dispatched', 'Running'])
        ).all()
        now = datetime.utcnow()
        # Correlated NOT EXISTS instead of a bound-parameter IN list: a large
        # backlog could exceed SQLite's variable limit and abort startup, which
        # left the whole engine unable to boot.
        has_active_task = (
            JudgeTask.query.filter(
                JudgeTask.submission_id == Submission.id,
                JudgeTask.status.in_(['Queued', 'Dispatched', 'Running']),
            )
            .exists()
            .correlate(Submission)
        )
        for task in active_tasks:
            if task.status in ('Dispatched', 'Running'):
                task.status = 'Queued'
                task.started_at = None
                task.worker_id = None
                task.last_heartbeat_at = now
                task.last_error = TASK_RECOVERY_MESSAGE
            submission = db.session.get(Submission, task.submission_id)
            if submission:
                submission.status = 'Queued'

        orphaned_queued = Submission.query.filter(
            Submission.status == 'Queued',
            ~has_active_task,
        ).all()
        for submission in orphaned_queued:
            existing = JudgeTask.query.filter_by(submission_id=submission.id).first()
            if existing:
                existing.status = 'Queued'
                existing.started_at = None
                existing.completed_at = None
                existing.worker_id = None
                existing.last_heartbeat_at = now
                existing.last_error = TASK_RECOVERY_MESSAGE
            else:
                db.session.add(
                    JudgeTask(
                        submission_id=submission.id,
                        status='Queued',
                        last_heartbeat_at=now,
                        last_error=TASK_RECOVERY_MESSAGE,
                    )
                )

        orphaned_judging = Submission.query.filter(
            Submission.status == 'Judging',
            ~has_active_task,
        ).all()
        for submission in orphaned_judging:
            submission.status = 'Failed'
            submission.error_message = TASK_RECOVERY_MESSAGE
        db.session.commit()

    def _reconcile_dead_workers(self):
        from app import db
        from app.models.judge_task import JudgeTask
        from app.models.submission import Submission

        live_names = {getattr(worker, 'name', None) for worker in self._live_worker_processes()}
        live_names.discard(None)
        for task in JudgeTask.query.filter_by(status='Running').all():
            if task.worker_id and task.worker_id not in live_names:
                submission = db.session.get(Submission, task.submission_id)
                self.execution_service.handle_task_failure(
                    task,
                    submission,
                    WORKER_LOST_MESSAGE,
                    retryable=True,
                )
                self._release_task_reservation(task.id)

    def _ensure_live_workers(self):
        with self._state_lock:
            if not self.is_running or self.stop_event.is_set():
                return
            live_count = self._live_worker_count()
            if live_count >= self.max_workers:
                return
            now = datetime.utcnow()
            if self._last_worker_restart_at and now - self._last_worker_restart_at < timedelta(
                seconds=5
            ):
                return
            next_index = len(self.worker_processes)
            worker = self._spawn_worker(next_index)
            if worker is not None:
                self.worker_processes.append(worker)
                self.workers.append(worker)

    def submit_judge_task(self, submission_id) -> bool:
        from app import db
        from app.models.judge_task import JudgeTask
        from app.models.submission import Submission

        with self._state_lock:
            if not self.is_running or self._live_worker_count() == 0:
                logger.warning(
                    'Rejecting submission_id=%s because judge engine is unavailable',
                    submission_id,
                )
                return False

            with self.app.app_context():
                submission = db.session.get(Submission, submission_id)
                if not submission:
                    return False

                existing = JudgeTask.query.filter(
                    JudgeTask.submission_id == submission_id,
                    JudgeTask.status.in_(['Queued', 'Running', 'Dispatched']),
                ).first()
                if existing:
                    return False

                task = JudgeTask(
                    submission_id=submission_id,
                    status='Queued',
                    last_heartbeat_at=datetime.utcnow(),
                )
                db.session.add(task)
                submission.status = 'Queued'

                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    return False

                self.notify_new_task()
                return True

    def _dispatcher_loop(self):
        while self.is_running and not self.stop_event.is_set():
            paused = False
            try:
                with self.app.app_context():
                    self._reconcile_dead_workers()
                    self._cleanup_stale_tasks()
                    self._ensure_live_workers()
                    self._dispatch_queued_tasks(limit=max(1, self.max_workers))
                    paused = bool(self.dispatch_pause_reason)
            except Exception as e:
                logger.error('Dispatcher error: %s', e)
            # A refused dispatch backs off; otherwise wait on the wakeup signal so a
            # new submission starts judging immediately instead of after a full tick.
            self._wakeup_event.clear()
            wait_seconds = self.host_backoff_seconds if paused else self.dispatch_poll_seconds
            if self.stop_event.is_set():
                break
            self._wakeup_event.wait(wait_seconds)

    def notify_new_task(self):
        """Wake the dispatcher so queued work is picked up without polling delay."""
        self._wakeup_event.set()

    def _dispatch_queued_tasks(self, limit=5):
        from app import db
        from app.models.judge_task import JudgeTask

        self._release_finished_task_reservations()
        required_memory_mb = self.policy.max_memory_limit_mb
        required_processes = self.policy.max_processes
        try:
            can_dispatch, reason = self.host_guard.can_dispatch(
                memory_mb=required_memory_mb,
                processes=required_processes,
            )
        except TypeError:
            # Keep small test/demonstration guards compatible with the old API.
            can_dispatch, reason = self.host_guard.can_dispatch()
        self.dispatch_pause_reason = reason
        if not can_dispatch:
            return 0

        tasks = (
            JudgeTask.query.filter_by(status='Queued')
            .order_by(JudgeTask.created_at.asc())
            .limit(limit)
            .all()
        )

        for task in tasks:
            reserve = getattr(self.host_guard, 'reserve', None)
            reservation = (
                reserve(required_memory_mb, required_processes) if callable(reserve) else None
            )
            if callable(reserve) and reservation is None:
                self.dispatch_pause_reason = 'reserved judge resource budget is exhausted'
                break
            dispatched_at = datetime.utcnow()
            claimed = JudgeTask.query.filter(
                JudgeTask.id == task.id,
                JudgeTask.status == 'Queued',
            ).update(
                {
                    JudgeTask.status: 'Dispatched',
                    JudgeTask.last_heartbeat_at: dispatched_at,
                },
                synchronize_session=False,
            )
            if claimed == 0:
                db.session.rollback()
                self._release_reservation(reservation)
                continue

            db.session.commit()

            try:
                self.task_queue.put_nowait(task.submission_id)
            except queue.Full:
                reverted = JudgeTask.query.filter(
                    JudgeTask.id == task.id,
                    JudgeTask.status == 'Dispatched',
                ).update(
                    {
                        JudgeTask.status: 'Queued',
                    },
                    synchronize_session=False,
                )
                if reverted:
                    db.session.commit()
                else:
                    db.session.rollback()
                self._release_reservation(reservation)
                break
            if reservation is not None:
                self._task_reservations[task.id] = reservation
        return len(tasks)

    def _release_reservation(self, reservation):
        if reservation is not None:
            release = getattr(self.host_guard, 'release', None)
            if callable(release):
                release(reservation)

    def _release_task_reservation(self, task_id):
        reservation = self._task_reservations.pop(task_id, None)
        self._release_reservation(reservation)

    def _release_finished_task_reservations(self):
        if not self._task_reservations:
            return
        from app.models.judge_task import JudgeTask

        task_ids = list(self._task_reservations)
        rows = JudgeTask.query.filter(JudgeTask.id.in_(task_ids)).all()
        statuses = {row.id: row.status for row in rows}
        for task_id in task_ids:
            if statuses.get(task_id) not in ('Queued', 'Dispatched', 'Running'):
                self._release_task_reservation(task_id)

    def _cleanup_stale_tasks(self):
        from app import db
        from app.models.judge_task import JudgeTask
        from app.models.submission import Submission

        now = datetime.utcnow()
        # Conservative SQL prefilter so the dispatcher no longer loads every active
        # task each tick. Dynamic Running timeouts are always >= task_timeout_ms, so
        # nothing excluded here could have been stale.
        min_timeout_ms = min(self.queued_task_timeout_ms, self.task_timeout_ms)
        last_seen_column = db.func.coalesce(
            JudgeTask.last_heartbeat_at,
            JudgeTask.started_at,
            JudgeTask.created_at,
        )
        stale_tasks = (
            JudgeTask.query.filter(
                JudgeTask.status.in_(['Queued', 'Running', 'Dispatched']),
                last_seen_column.isnot(None),
                last_seen_column < now - timedelta(milliseconds=min_timeout_ms),
            )
            .order_by(JudgeTask.id.asc())
            .limit(200)
            .all()
        )

        for task in stale_tasks:
            last_seen = task.last_heartbeat_at or task.started_at or task.created_at
            if not last_seen:
                continue

            if task.status == 'Queued':
                timeout_ms = self.queued_task_timeout_ms
            elif task.status == 'Running':
                timeout_ms = self._dynamic_task_timeout(task)
            else:
                timeout_ms = self.task_timeout_ms

            if now - last_seen <= timedelta(milliseconds=timeout_ms):
                continue

            if task.status == 'Queued':
                submission = db.session.get(Submission, task.submission_id)
                task.status = 'Failed'
                task.completed_at = now
                task.last_error = STALE_QUEUE_MESSAGE
                if submission:
                    submission.status = 'Failed'
                    submission.error_message = STALE_QUEUE_MESSAGE
                db.session.commit()
                self._release_task_reservation(task.id)
                continue

            submission = db.session.get(Submission, task.submission_id)
            if task.status == 'Dispatched':
                task.status = 'Queued'
                task.worker_id = None
                task.last_heartbeat_at = datetime.utcnow()
                if submission and submission.status in ('Queued', 'Judging'):
                    submission.status = 'Queued'
                db.session.commit()
                self._task_timeout_cache.pop(task.id, None)
                self._release_task_reservation(task.id)
                continue

            self.execution_service.handle_task_failure(
                task,
                submission,
                'Task timeout cleanup',
                retryable=True,
            )
            self._release_task_reservation(task.id)
            self._task_timeout_cache.pop(task.id, None)

    def _dynamic_task_timeout(self, task):
        cached = self._task_timeout_cache.get(task.id)
        if cached is not None:
            return cached
        timeout = self._compute_task_timeout(task.submission_id)
        if len(self._task_timeout_cache) >= 10000:
            self._task_timeout_cache.clear()
        self._task_timeout_cache[task.id] = timeout
        return timeout

    def _compute_task_timeout(self, submission_id):
        from app import db
        from app.models.problem import Problem
        from app.models.submission import Submission
        from app.utils.file_utils import count_test_cases

        base_timeout = self.task_timeout_ms
        if not submission_id:
            return base_timeout

        sub = Submission.query.filter_by(id=submission_id).first()
        if not sub or not sub.problem_id:
            return base_timeout

        problem = db.session.get(Problem, sub.problem_id)
        if not problem:
            return base_timeout

        time_limit_ms = problem.time_limit or 1000
        case_count = count_test_cases(sub.problem_id)
        if case_count <= 0:
            case_count = 1

        max_runtime_ms = time_limit_ms * case_count
        safety_margin = max(30000, base_timeout)
        dynamic = max_runtime_ms + safety_margin
        return max(base_timeout, min(dynamic, 7200000))


def _worker_process(config_name, task_queue, stop_event, max_retries, log_dir, worker_config):
    from app import create_app
    from app.judge.sandbox import apply_judge_background_priority

    apply_judge_background_priority()

    overrides = {k: v for k, v in worker_config.items() if v is not None}

    app = create_app(config_name, start_judge_engine=False, config_overrides=overrides)
    engine = _WorkerJudge(app, task_queue, max_retries, log_dir)
    engine.run(stop_event)


class _WorkerJudge:
    def __init__(self, app, task_queue, max_retries, log_dir):
        self.app = app
        self.task_queue = task_queue
        self.execution_service = _JudgeExecutionService(app, max_retries, log_dir)

    def run(self, stop_event):
        from multiprocessing import current_process

        with self.app.app_context():
            while not stop_event.is_set():
                try:
                    submission_id = self.task_queue.get(timeout=1)
                    if submission_id is None:
                        break
                    try:
                        self._judge_submission(submission_id, current_process().name)
                    finally:
                        self.task_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error('Worker error: %s', e)

    def _judge_submission(self, submission_id, worker_name):
        from app import db
        from app.models.judge_task import JudgeTask
        from app.models.submission import Submission

        task = JudgeTask.query.filter_by(submission_id=submission_id).first()
        if not task:
            logger.error('Task not found for submission_id=%s', submission_id)
            return

        started_at = datetime.utcnow()
        claimed = JudgeTask.query.filter(
            JudgeTask.id == task.id,
            JudgeTask.status == 'Dispatched',
        ).update(
            {
                JudgeTask.status: 'Running',
                JudgeTask.started_at: started_at,
                JudgeTask.last_heartbeat_at: started_at,
                JudgeTask.worker_id: worker_name,
            },
            synchronize_session=False,
        )

        if claimed == 0:
            db.session.rollback()
            logger.info(
                'Skip submission_id=%s because task is not in Dispatched state',
                submission_id,
            )
            return

        submission = db.session.get(Submission, submission_id)
        if submission:
            submission.status = 'Judging'
        db.session.commit()

        task = db.session.get(JudgeTask, task.id)
        if not task or not submission:
            if task:
                self.execution_service.handle_task_failure(
                    task,
                    None,
                    'Task or submission not found before judging',
                    retryable=False,
                )
            return

        try:
            result = self.execution_service.execute_judge(submission, task)

            refreshed_task = db.session.get(JudgeTask, task.id)
            refreshed_submission = db.session.get(Submission, submission_id)
            if not refreshed_task or not refreshed_submission:
                return

            if refreshed_task.status != 'Running' or refreshed_task.worker_id != worker_name:
                logger.info(
                    'Task for submission_id=%s was superseded (status=%s, worker=%s); '
                    'discarding result from %s',
                    submission_id,
                    refreshed_task.status,
                    refreshed_task.worker_id,
                    worker_name,
                )
                return

            refreshed_submission.status = result.get('status', 'Failed')
            refreshed_submission.time_used = result.get('time_used')
            refreshed_submission.memory_used = result.get('memory_used')
            refreshed_submission.error_message = result.get('error_message')
            refreshed_submission.test_case_passed = result.get('passed', 0)
            refreshed_submission.test_case_total = result.get('total', 0)
            refreshed_submission.judged_at = datetime.utcnow()
            refreshed_task.completed_at = datetime.utcnow()

            if self.execution_service.should_retry(
                result.get('status'), result.get('error_message', '')
            ):
                self.execution_service.handle_task_failure(
                    refreshed_task,
                    refreshed_submission,
                    result.get('error_message', ''),
                    retryable=True,
                )
            else:
                refreshed_task.status = 'Completed'
                db.session.commit()
        except Exception as e:
            logger.error('Judge submission error: %s', e)
            db.session.rollback()
            try:
                failed_task = JudgeTask.query.filter_by(submission_id=submission_id).first()
                failed_submission = db.session.get(Submission, submission_id)
                if failed_task:
                    self.execution_service.handle_task_failure(
                        failed_task,
                        failed_submission,
                        str(e),
                        retryable=True,
                    )
            except Exception:
                db.session.rollback()
