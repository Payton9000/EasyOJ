import logging
import queue
import threading
from datetime import datetime

logger = logging.getLogger(__name__)


class JudgeEngine:
    def __init__(self, app):
        self.app = app
        self.task_queue = queue.Queue(maxsize=100)
        self.workers = []
        self.max_workers = app.config.get('MAX_JUDGE_WORKERS', 3)
        self.is_running = False

    def start(self):
        self.is_running = True
        for i in range(self.max_workers):
            t = threading.Thread(target=self._worker_loop, name=f'JudgeWorker-{i}', daemon=True)
            t.start()
            self.workers.append(t)
        dispatcher = threading.Thread(target=self._dispatcher_loop, name='JudgeDispatcher', daemon=True)
        dispatcher.start()
        self.workers.append(dispatcher)
        logger.info('JudgeEngine started with %d workers', self.max_workers)

    def stop(self):
        self.is_running = False
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
                    tasks = JudgeTask.query.filter_by(status='Queued').order_by(
                        JudgeTask.created_at.asc()).limit(5).all()
                    for task in tasks:
                        try:
                            self.task_queue.put_nowait(task.submission_id)
                            task.status = 'Dispatched'
                            db.session.commit()
                        except queue.Full:
                            break
                except Exception as e:
                    logger.error('Dispatcher error: %s', e)
                time.sleep(1)

    def _worker_loop(self):
        with self.app.app_context():
            while self.is_running:
                try:
                    submission_id = self.task_queue.get(timeout=1)
                    try:
                        self._judge_submission(submission_id)
                    finally:
                        self.task_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error('Worker error: %s', e)

    def _judge_submission(self, submission_id):
        from app.models.judge_task import JudgeTask
        from app.models.submission import Submission
        from app import db

        with self.app.app_context():
            task = JudgeTask.query.filter_by(submission_id=submission_id).first()
            submission = Submission.query.get(submission_id)

            if not task or not submission:
                logger.error('Task or submission not found for submission_id=%s', submission_id)
                return

            try:
                task.status = 'Running'
                task.started_at = datetime.utcnow()
                task.worker_id = threading.current_thread().name
                submission.status = 'Judging'
                db.session.commit()

                result = self._execute_judge(submission)

                submission.status = result.get('status', 'Failed')
                submission.time_used = result.get('time_used')
                submission.memory_used = result.get('memory_used')
                submission.error_message = result.get('error_message')
                submission.test_case_passed = result.get('passed', 0)
                submission.test_case_total = result.get('total', 0)
                submission.judged_at = datetime.utcnow()

                task.status = 'Completed'
                task.completed_at = datetime.utcnow()
                db.session.commit()
            except Exception as e:
                logger.error('Judge submission error: %s', e)
                try:
                    task.status = 'Failed'
                    submission.status = 'Failed'
                    db.session.commit()
                except Exception:
                    pass

    def _execute_judge(self, submission) -> dict:
        from app.utils.file_utils import create_judge_workspace, write_code_file, load_test_cases, cleanup_dir
        from app.judge.compiler import Compiler
        from app.judge.executor import Executor
        from app.judge.comparator import Comparator

        work_dir = None
        try:
            work_dir = create_judge_workspace(submission.id)
            source_path = write_code_file(work_dir, submission.code, submission.language)

            compiler = Compiler(self.app)
            executor = Executor(self.app)
            comparator = Comparator()

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
            time_limit = problem.time_limit if problem else 1000
            memory_limit = problem.memory_limit if problem else 256

            max_time = 0
            max_memory = 0
            passed = 0
            total = len(test_cases)

            for i, (input_data, expected_output) in enumerate(test_cases, 1):
                exec_result = executor.execute(
                    work_dir, submission.language, input_data, time_limit, memory_limit
                )
                status = exec_result.get('status', 'RE')
                if status != 'OK':
                    return {
                        'status': status,
                        'error_message': exec_result.get('error', ''),
                        'time_used': exec_result.get('time_used', 0),
                        'memory_used': exec_result.get('memory_used', 0),
                        'passed': passed,
                        'total': total,
                    }
                if not comparator.compare(exec_result.get('output', ''), expected_output):
                    return {
                        'status': 'WA',
                        'error_message': f'Wrong answer on test case {i}',
                        'time_used': exec_result.get('time_used', 0),
                        'memory_used': exec_result.get('memory_used', 0),
                        'passed': passed,
                        'total': total,
                    }
                passed += 1
                max_time = max(max_time, exec_result.get('time_used', 0))
                max_memory = max(max_memory, exec_result.get('memory_used', 0))

            return {
                'status': 'AC',
                'time_used': max_time,
                'memory_used': max_memory,
                'passed': total,
                'total': total,
            }
        finally:
            if work_dir:
                cleanup_dir(work_dir)
