import subprocess
import threading
import time
import logging

logger = logging.getLogger(__name__)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


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


class WindowsSandbox:
    @staticmethod
    def run_with_limits(command, input_data=None, time_limit=1000, memory_limit=256,
                        work_dir=None) -> dict:
        kwargs = {
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'text': True,
            'cwd': work_dir,
        }
        if input_data is not None:
            kwargs['stdin'] = subprocess.PIPE
        if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP'):
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP

        status = 'OK'
        output = ''
        error = ''

        try:
            process = subprocess.Popen(command, **kwargs)
            monitor = ProcessMonitor(process, memory_limit)
            monitor.start()

            try:
                stdout, stderr = process.communicate(
                    input=input_data, timeout=time_limit / 1000.0)
                output = stdout
                error = stderr
                if process.returncode != 0:
                    status = 'RE'
            except subprocess.TimeoutExpired:
                _kill_process_tree(process.pid)
                process.kill()
                process.communicate()
                status = 'TLE'
            finally:
                monitor.stop()

            if monitor.killed_due_to_memory:
                status = 'MLE'

            return {
                'status': status,
                'output': output,
                'error': error,
                'time_used': int(monitor.max_time_ms),
                'memory_used': int(monitor.max_memory_kb),
            }
        except Exception as e:
            return {
                'status': 'RE',
                'output': '',
                'error': str(e),
                'time_used': 0,
                'memory_used': 0,
            }
