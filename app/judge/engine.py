import json
import logging
import multiprocessing
import os
import queue
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class JudgeEngine:
    def __init__(self, app, config_name='default'):
        self.app = app
        self.config_name = config_name
        self.db_uri = app.config.get('SQLALCHEMY_DATABASE_URI')
        self.base_dir = app.config.get('BASE_DIR')
        queue_size = app.config.get('JUDGE_QUEUE_MAXSIZE', 100)
        self.mp_ctx = multiprocessing.get_context('spawn')
        self.task_queue = self.mp_ctx.JoinableQueue(maxsize=queue_size)
        self.workers = []
        self.max_workers = app.config.get('MAX_JUDGE_WORKERS', 3)
        self.task_timeout_ms = app.config.get('JUDGE_TASK_TIMEOUT_MS', 180000)
        self.max_retries = app.config.get('JUDGE_TASK_MAX_RETRIES', 2)
        self.log_dir = app.config.get('JUDGE_LOG_DIR')
        self.is_running = False
        self.stop_event = self.mp_ctx.Event()

        if self.log_dir:
            os.makedirs(self.log_dir, exist_ok=True)

    def start(self):
        self.is_running = True
        self.stop_event.clear()
        for i in range(self.max_workers):
            p = self.mp_ctx.Process(
                target=_worker_process,
                name=f'JudgeWorker-{i}',
                args=(
                    self.config_name,
                    self.task_queue,
                    self.stop_event,
                    self.max_retries,
                    self.log_dir,
                    self.db_uri,
                    self.base_dir,
                ),
            )
            p.start()
            self.workers.append(p)
        dispatcher = threading.Thread(target=self._dispatcher_loop, name='JudgeDispatcher', daemon=True)
        dispatcher.start()
        self.workers.append(dispatcher)
        logger.info('JudgeEngine started with %d workers', self.max_workers)

    def stop(self):
        self.is_running = False
        self.stop_event.set()
        for _ in range(self.max_workers):
            try:
                self.task_queue.put_nowait(None)
            except queue.Full:
                break
        for t in self.workers:
            t.join(timeout=5)
        logger.info('JudgeEngine stopped')

    def submit_judge_task(self, submission_id) -> bool:
        from app.models.judge_task import JudgeTask
        from app.models.submission import Submission
        from app import db

        with self.app.app_context():
            existing = JudgeTask.query.filter(
                JudgeTask.submission_id == submission_id,
                JudgeTask.status.in_(['Queued', 'Running', 'Dispatched'])
            ).first()
            if existing:
                return False

            task = JudgeTask(submission_id=submission_id, status='Queued')
            db.session.add(task)

            submission = Submission.query.get(submission_id)
            if submission:
                submission.status = 'Queued'

            db.session.commit()

            try:
                self.task_queue.put_nowait(submission_id)
                return True
            except queue.Full:
                task.status = 'Failed'
                if submission:
                    submission.status = 'Failed'
                db.session.commit()
                return False

    def _dispatcher_loop(self):
        import time
        from app.models.judge_task import JudgeTask
        from app import db

        with self.app.app_context():
            while self.is_running:
                try:
                    self._cleanup_stale_tasks()
                    tasks = JudgeTask.query.filter_by(status='Queued').order_by(
                        JudgeTask.created_at.asc()).limit(5).all()
                    for task in tasks:
                        try:
                            self.task_queue.put_nowait(task.submission_id)
                            task.status = 'Dispatched'
                            task.last_heartbeat_at = datetime.utcnow()
                            db.session.commit()
                        except queue.Full:
                            break
                except Exception as e:
                    logger.error('Dispatcher error: %s', e)
                time.sleep(1)

    def _execute_judge(self, submission, task) -> dict:
        from app.utils.file_utils import create_judge_workspace, write_code_file, load_test_cases, cleanup_dir
        from app.judge.compiler import Compiler
        from app.judge.executor import Executor
        from app.judge.comparator import Comparator
        from app import db

        work_dir = None
        case_logs = []
        try:
            work_dir = create_judge_workspace(submission.id)
            source_path = write_code_file(work_dir, submission.code, submission.language)

            compiler = Compiler(self.app)
            executor = Executor(self.app)
            comparator = Comparator()
            cfg = self.app.config

            # Compile if needed
            if submission.language in ('cpp', 'java'):
                compile_result = compiler.compile(source_path, submission.language, work_dir)
                if not compile_result['success']:
                    return {
                        'status': 'CE',
                        'error_message': compile_result['error'],
                        'passed': 0,
                        'total': 0,
                    }
                executable = compile_result['executable']
            else:
                executable = source_path

            # Load test cases
            test_cases = load_test_cases(submission.problem_id)
            if not test_cases:
                return {'status': 'Failed', 'error_message': 'No test cases', 'passed': 0, 'total': 0}

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
            total = len(test_cases)

            for i, (input_data, expected_output) in enumerate(test_cases, 1):
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
                task.last_heartbeat_at = datetime.utcnow()
                db.session.commit()
                if status != 'OK':
                    self._write_judge_log(submission.id, case_logs, status)
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
                    self._write_judge_log(submission.id, case_logs, 'WA')
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

            self._write_judge_log(submission.id, case_logs, 'AC')

            return {
                'status': 'AC',
                'time_used': max_time_used,
                'memory_used': max_memory_used,
                'passed': total,
                'total': total,
            }
        except Exception as e:
            self._write_judge_log(submission.id, case_logs, 'SystemError', str(e))
            return {'status': 'SystemError', 'error_message': str(e), 'passed': 0, 'total': 0}
        finally:
            if work_dir:
                cleanup_dir(work_dir)

    def _cleanup_stale_tasks(self):
        from app.models.judge_task import JudgeTask
        from app.models.submission import Submission
        from app import db

        timeout_delta = timedelta(milliseconds=self.task_timeout_ms)
        now = datetime.utcnow()
        stale_tasks = JudgeTask.query.filter(JudgeTask.status == 'Running').all()
        for task in stale_tasks:
            last_seen = task.last_heartbeat_at or task.started_at
            if last_seen and now - last_seen > timeout_delta:
                submission = Submission.query.get(task.submission_id)
                self._handle_task_failure(task, submission, 'Task timeout cleanup', retryable=True)

    def _should_retry(self, status):
        return status in ('Failed', 'SystemError')

    def _handle_task_failure(self, task, submission, error_message, retryable=False):
        from app import db

        task.last_error = (error_message or '')[:1000]
        if retryable and task.retry_count < self.max_retries:
            task.retry_count += 1
            task.status = 'Queued'
            task.last_heartbeat_at = datetime.utcnow()
            if submission:
                submission.status = 'Queued'
            db.session.commit()
            try:
                self.task_queue.put_nowait(task.submission_id)
                logger.warning('Retrying submission_id=%s (attempt %s)',
                               task.submission_id, task.retry_count)
                return
            except queue.Full:
                task.status = 'Failed'

        task.status = 'Failed'
        task.completed_at = datetime.utcnow()
        if submission:
            submission.status = 'Failed'
        db.session.commit()

    def _write_judge_log(self, submission_id, case_logs, final_status, error_message=None):
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
            from app.models.judge_task import JudgeTask
            from app import db
            task = JudgeTask.query.filter_by(submission_id=submission_id).first()
            if task:
                task.debug_log_path = log_path
                db.session.commit()
            return log_path
        except Exception as e:
            logger.error('Failed to write judge log: %s', e)
            return None


def _worker_process(config_name, task_queue, stop_event, max_retries, log_dir, db_uri, base_dir):
    from app import create_app

    overrides = {}
    if db_uri:
        overrides['SQLALCHEMY_DATABASE_URI'] = db_uri
    if base_dir:
        overrides['BASE_DIR'] = base_dir
    app = create_app(config_name, start_judge_engine=False, config_overrides=overrides)
    engine = _WorkerJudge(app, task_queue, max_retries, log_dir)
    engine.run(stop_event)


class _WorkerJudge:
    def __init__(self, app, task_queue, max_retries, log_dir):
        self.app = app
        self.task_queue = task_queue
        self.max_retries = max_retries
        self.log_dir = log_dir
        if self.log_dir:
            os.makedirs(self.log_dir, exist_ok=True)

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
        from app.models.judge_task import JudgeTask
        from app.models.submission import Submission
        from app import db

        task = JudgeTask.query.filter_by(submission_id=submission_id).first()
        submission = Submission.query.get(submission_id)

        if not task or not submission:
            logger.error('Task or submission not found for submission_id=%s', submission_id)
            return

        try:
            task.status = 'Running'
            task.started_at = datetime.utcnow()
            task.last_heartbeat_at = task.started_at
            task.worker_id = worker_name
            submission.status = 'Judging'
            db.session.commit()

            result = self._execute_judge(submission, task)

            submission.status = result.get('status', 'Failed')
            submission.time_used = result.get('time_used')
            submission.memory_used = result.get('memory_used')
            submission.error_message = result.get('error_message')
            submission.test_case_passed = result.get('passed', 0)
            submission.test_case_total = result.get('total', 0)
            submission.judged_at = datetime.utcnow()

            task.completed_at = datetime.utcnow()

            if self._should_retry(result.get('status')):
                self._handle_task_failure(task, submission, result.get('error_message', ''),
                                          retryable=True)
            else:
                task.status = 'Completed'
                db.session.commit()
        except Exception as e:
            logger.error('Judge submission error: %s', e)
            try:
                self._handle_task_failure(task, submission, str(e), retryable=True)
            except Exception:
                pass

    def _execute_judge(self, submission, task) -> dict:
        from app.utils.file_utils import create_judge_workspace, write_code_file, load_test_cases, cleanup_dir
        from app.judge.compiler import Compiler
        from app.judge.executor import Executor
        from app.judge.comparator import Comparator
        from app import db

        work_dir = None
        case_logs = []
        try:
            work_dir = create_judge_workspace(submission.id)
            source_path = write_code_file(work_dir, submission.code, submission.language)

            compiler = Compiler(self.app)
            executor = Executor(self.app)
            comparator = Comparator()
            cfg = self.app.config

            if submission.language in ('cpp', 'java'):
                compile_result = compiler.compile(source_path, submission.language, work_dir)
                if not compile_result['success']:
                    return {
                        'status': 'CE',
                        'error_message': compile_result['error'],
                        'passed': 0,
                        'total': 0,
                    }
                executable = compile_result['executable']
            else:
                executable = source_path

            test_cases = load_test_cases(submission.problem_id)
            if not test_cases:
                return {'status': 'Failed', 'error_message': 'No test cases', 'passed': 0, 'total': 0}

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
            total = len(test_cases)

            for i, (input_data, expected_output) in enumerate(test_cases, 1):
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
                task.last_heartbeat_at = datetime.utcnow()
                db.session.commit()
                if status != 'OK':
                    self._write_judge_log(submission.id, case_logs, status)
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
                    self._write_judge_log(submission.id, case_logs, 'WA')
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

            self._write_judge_log(submission.id, case_logs, 'AC')

            return {
                'status': 'AC',
                'time_used': max_time_used,
                'memory_used': max_memory_used,
                'passed': total,
                'total': total,
            }
        except Exception as e:
            self._write_judge_log(submission.id, case_logs, 'SystemError', str(e))
            return {'status': 'SystemError', 'error_message': str(e), 'passed': 0, 'total': 0}
        finally:
            if work_dir:
                cleanup_dir(work_dir)

    def _should_retry(self, status):
        return status in ('Failed', 'SystemError')

    def _handle_task_failure(self, task, submission, error_message, retryable=False):
        from app import db

        task.last_error = (error_message or '')[:1000]
        if retryable and task.retry_count < self.max_retries:
            task.retry_count += 1
            task.status = 'Queued'
            task.last_heartbeat_at = datetime.utcnow()
            if submission:
                submission.status = 'Queued'
            db.session.commit()
            try:
                self.task_queue.put_nowait(task.submission_id)
                logger.warning('Retrying submission_id=%s (attempt %s)',
                               task.submission_id, task.retry_count)
                return
            except queue.Full:
                task.status = 'Failed'

        task.status = 'Failed'
        task.completed_at = datetime.utcnow()
        if submission:
            submission.status = 'Failed'
        db.session.commit()

    def _write_judge_log(self, submission_id, case_logs, final_status, error_message=None):
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
            from app.models.judge_task import JudgeTask
            from app import db
            task = JudgeTask.query.filter_by(submission_id=submission_id).first()
            if task:
                task.debug_log_path = log_path
                db.session.commit()
            return log_path
        except Exception as e:
            logger.error('Failed to write judge log: %s', e)
            return None
