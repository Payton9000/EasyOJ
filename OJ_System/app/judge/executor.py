import logging
import os
import subprocess
import threading
import time

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

    def execute(self, work_dir, language, input_data, time_limit, memory_limit) -> dict:
        cfg = self._get_config()
        compiler_paths = cfg.get('COMPILER_PATHS', {})

        if language == 'cpp':
            cmd = [os.path.join(work_dir, 'main.exe')]
        elif language == 'java':
            java = compiler_paths.get('java', 'java')
            cmd = [java, '-cp', work_dir, 'Main']
        elif language == 'python':
            python = compiler_paths.get('python', 'python')
            cmd = [python, os.path.join(work_dir, 'main.py')]
        else:
            return {'status': 'RE', 'output': '', 'time_used': 0, 'memory_used': 0,
                    'error': f'Unknown language: {language}'}

        kwargs = {
            'stdin': subprocess.PIPE,
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'text': True,
            'cwd': work_dir,
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

            try:
                stdout, stderr = process.communicate(
                    input=input_data, timeout=time_limit / 1000.0)
                output = stdout
                error = stderr
            except subprocess.TimeoutExpired:
                _kill_process_tree(process.pid)
                process.kill()
                process.communicate()
                status = 'TLE'
            finally:
                monitor.stop()

            time_used = int(monitor.max_time_ms)
            memory_used = int(monitor.max_memory_kb)

            if monitor.killed_due_to_memory:
                status = 'MLE'
            elif status == 'OK' and process.returncode != 0:
                status = 'RE'

        except FileNotFoundError as e:
            return {'status': 'RE', 'output': '', 'time_used': 0, 'memory_used': 0,
                    'error': f'Executable not found: {e}'}
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
