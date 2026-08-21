import logging
import subprocess
import threading
import time

from app.judge.languages import DEFAULT_LANGUAGE_SPECS
from app.judge.languages import build_run_command

logger = logging.getLogger(__name__)

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning('psutil not available; memory monitoring disabled')


class ProcessMonitor:
    def __init__(self, process, memory_limit_mb):
        self.process = process
        self.memory_limit_kb = memory_limit_mb * 1024
        self.max_time_ms = 0
        self.max_memory_kb = 0
        self.killed_due_to_memory = False
        self.running = False
        self._thread = None

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=1)

    def _monitor_loop(self):
        if not PSUTIL_AVAILABLE:
            return
        try:
            proc = psutil.Process(self.process.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return

        while self.running and self.process.poll() is None:
            try:
                mem_kb = proc.memory_info().rss / 1024
                self.max_memory_kb = max(self.max_memory_kb, mem_kb)
                if mem_kb > self.memory_limit_kb:
                    self.killed_due_to_memory = True
                    _kill_process_tree(self.process.pid)
                    break
                cpu = proc.cpu_times()
                self.max_time_ms = max(self.max_time_ms, (cpu.user + cpu.system) * 1000)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            time.sleep(0.01)


def _kill_process_tree(pid):
    if not PSUTIL_AVAILABLE:
        return
    try:
        proc = psutil.Process(pid)
        children = proc.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        gone, alive = psutil.wait_procs(children, timeout=3)
        for p in alive:
            try:
                p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


class Executor:
    def __init__(self, app=None):
        self.app = app

    def _get_config(self):
        if self.app:
            return self.app.config
        from flask import current_app

        return current_app.config

    def build_run_command(self, work_dir, language, memory_limit_mb=256):
        try:
            config = self._get_config()
        except RuntimeError:
            config = {'SUPPORTED_LANGUAGES': DEFAULT_LANGUAGE_SPECS}
        return build_run_command(
            config,
            work_dir,
            language,
            config.get('COMPILER_PATHS', {}),
            memory_limit_mb,
        )

    def execute(self, work_dir, language, input_data, time_limit, memory_limit) -> dict:
        cfg = self._get_config()

        time_limit = max(1, int(time_limit))
        memory_limit = max(1, int(memory_limit))

        try:
            cmd = self.build_run_command(work_dir, language, memory_limit)
        except ValueError as exc:
            return {
                'status': 'RE',
                'output': '',
                'time_used': 0,
                'memory_used': 0,
                'error': str(exc),
            }
        compiler_paths = cfg.get('COMPILER_PATHS', {})

        sandbox_enabled = bool(cfg.get('SANDBOX_ENABLED'))
        if sandbox_enabled:
            try:
                from app.judge.sandbox import SandboxRunner
                from app.judge.sandbox import is_supported

                if not is_supported():
                    return {
                        'status': 'SystemError',
                        'output': '',
                        'time_used': 0,
                        'memory_used': 0,
                        'error': 'Sandbox enabled but not supported on this host',
                    }
                runner = SandboxRunner(cfg)
                return runner.run(
                    cmd,
                    work_dir,
                    input_data or '',
                    time_limit,
                    memory_limit,
                    compiler_paths,
                    language,
                )
            except Exception as e:
                return {
                    'status': 'SystemError',
                    'output': '',
                    'time_used': 0,
                    'memory_used': 0,
                    'error': f'Sandbox failure: {e}',
                }

        if cfg.get('JUDGE_REQUIRE_SANDBOX', True):
            return {
                'status': 'SystemError',
                'output': '',
                'time_used': 0,
                'memory_used': 0,
                'error': 'Sandbox is required and cannot be disabled for this environment.',
            }

        kwargs = {
            'stdin': subprocess.PIPE,
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'text': True,
            'cwd': work_dir,
            'shell': False,
        }
        # Windows-specific
        if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP'):
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP

        status = 'OK'
        output = ''
        error = ''
        time_used = 0
        memory_used = 0

        try:
            process = subprocess.Popen(cmd, **kwargs)
            monitor = ProcessMonitor(process, memory_limit)
            monitor.start()

            start_ts = time.monotonic()

            try:
                stdout, stderr = process.communicate(input=input_data, timeout=time_limit / 1000.0)
                output = stdout
                error = stderr
            except subprocess.TimeoutExpired:
                _kill_process_tree(process.pid)
                process.kill()
                process.communicate()
                status = 'TLE'
            finally:
                monitor.stop()
                end_ts = time.monotonic()

            wall_ms = int((end_ts - start_ts) * 1000)
            time_used = int(max(monitor.max_time_ms, wall_ms))
            memory_used = int(monitor.max_memory_kb)

            if monitor.killed_due_to_memory:
                status = 'MLE'
            elif status == 'OK' and process.returncode != 0:
                status = 'RE'

        except FileNotFoundError as e:
            return {
                'status': 'RE',
                'output': '',
                'time_used': 0,
                'memory_used': 0,
                'error': f'Executable not found: {e}',
            }
        except Exception as e:
            return {'status': 'RE', 'output': '', 'time_used': 0, 'memory_used': 0, 'error': str(e)}

        max_output = self._get_config().get('MAX_OUTPUT_SIZE', 64 * 1024)
        if len(output) > max_output:
            output = output[:max_output]

        return {
            'status': status,
            'output': output,
            'time_used': time_used,
            'memory_used': memory_used,
            'error': error,
        }
