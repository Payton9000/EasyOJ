import threading
from dataclasses import dataclass

from app.judge.compiler import Compiler
from app.judge.executor import Executor
from app.judge.host_guard import HostCapacityGuard
from app.utils.file_utils import cleanup_dir
from app.utils.file_utils import create_judge_workspace
from app.utils.file_utils import write_code_file
from app.utils.security import sanitize_code


@dataclass(frozen=True)
class PracticeRunResult:
    status: str
    output: str
    error: str
    time_used: int
    memory_used: int


class PracticeRunService:
    def __init__(self, app):
        self.app = app
        self.host_guard = HostCapacityGuard(
            app.config.get('JUDGE_HOST_MAX_CPU_PERCENT', 100),
            app.config.get('JUDGE_HOST_MIN_AVAILABLE_MEMORY_MB', 1024),
        )
        self._semaphore = threading.BoundedSemaphore(
            max(1, int(app.config.get('PRACTICE_RUN_MAX_CONCURRENCY', 1)))
        )

    def validate_request(self, language, code, input_data):
        if not isinstance(language, str) or language not in self.app.config['SUPPORTED_LANGUAGES']:
            return PracticeRunResult('Invalid', '', 'Unsupported language', 0, 0)
        if not isinstance(code, str) or not code:
            return PracticeRunResult('Invalid', '', 'Code is required', 0, 0)
        if len(code) > 64 * 1024:
            return PracticeRunResult('Invalid', '', 'Code exceeds 64KB limit', 0, 0)
        if not isinstance(input_data, str):
            return PracticeRunResult('Invalid', '', 'Custom input must be text', 0, 0)
        if len(input_data.encode('utf-8')) > 32 * 1024:
            return PracticeRunResult('Invalid', '', 'Custom input exceeds 32KB limit', 0, 0)
        try:
            sanitize_code(code, language)
        except ValueError as exc:
            return PracticeRunResult('Invalid', '', str(exc), 0, 0)
        return None

    def try_acquire(self):
        if self._semaphore.acquire(blocking=False):
            return None
        return PracticeRunResult('Busy', '', 'A custom run is already in progress', 0, 0)

    def run(self, problem, language, code, input_data):
        invalid = self.validate_request(language, code, input_data)
        if invalid:
            return invalid
        can_run, reason = self.host_guard.can_dispatch()
        if not can_run:
            return PracticeRunResult('Busy', '', f'Host is busy: {reason}', 0, 0)
        busy = self.try_acquire()
        if busy:
            return busy

        work_dir = None
        try:
            work_dir = create_judge_workspace(f'practice_{threading.get_ident()}')
            source_path = write_code_file(work_dir, code, language)
            compiler = Compiler(self.app)
            if language in ('cpp', 'java'):
                compile_result = compiler.compile(source_path, language, work_dir)
                if not compile_result.get('success'):
                    return PracticeRunResult(
                        'CE', '', compile_result.get('error', 'Compilation failed'), 0, 0
                    )

            time_limit = min(
                max(1, int(problem.time_limit or 1000)),
                int(self.app.config.get('PRACTICE_RUN_TIMEOUT_MS', 5000)),
                int(self.app.config.get('MAX_TIME_LIMIT_MS', 20000)),
            )
            memory_limit = min(
                max(1, int(problem.memory_limit or 256)),
                int(self.app.config.get('MAX_MEMORY_LIMIT_MB', 512)),
            )
            result = Executor(self.app).execute(
                work_dir,
                language,
                input_data,
                time_limit,
                memory_limit,
            )
            return PracticeRunResult(
                result.get('status', 'SystemError'),
                result.get('output', ''),
                result.get('error', ''),
                int(result.get('time_used', 0) or 0),
                int(result.get('memory_used', 0) or 0),
            )
        except Exception as exc:
            self.app.logger.exception('Practice run failed')
            return PracticeRunResult('SystemError', '', str(exc), 0, 0)
        finally:
            if work_dir:
                cleanup_dir(work_dir)
            self._semaphore.release()
