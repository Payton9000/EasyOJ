from types import SimpleNamespace

import pytest

from app.judge import sandbox
from app.judge.host_guard import HostCapacityGuard


class _FakeJob:
    def __init__(self):
        self.info = {
            'BasicLimitInformation': {
                'LimitFlags': 0,
                'ActiveProcessLimit': 0,
                'PerProcessUserTimeLimit': 0,
            },
            'ProcessMemoryLimit': 0,
            'JobMemoryLimit': 0,
        }


class _FakeWin32Job:
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 1
    JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 2
    JOB_OBJECT_LIMIT_PROCESS_TIME = 4
    JOB_OBJECT_LIMIT_PROCESS_MEMORY = 8
    JOB_OBJECT_LIMIT_JOB_MEMORY = 16
    JobObjectExtendedLimitInformation = object()

    def CreateJobObject(self, _attributes, _name):
        return _FakeJob()

    def QueryInformationJobObject(self, job, _kind):
        return job.info

    def SetInformationJobObject(self, job, _kind, info):
        job.info = info


def test_job_object_sets_aggregate_memory_limit_and_process_limit(monkeypatch):
    fake_job_api = _FakeWin32Job()
    monkeypatch.setattr(sandbox, 'win32job', fake_job_api, raising=False)

    job = sandbox._create_job_object(2_000, 128, 4)

    limits = job.info['BasicLimitInformation']
    assert limits['ActiveProcessLimit'] == 4
    assert limits['LimitFlags'] & fake_job_api.JOB_OBJECT_LIMIT_JOB_MEMORY
    assert job.info['JobMemoryLimit'] == 128 * 1024 * 1024


def test_process_tree_usage_counts_child_memory_and_processes(monkeypatch):
    class _FakeProcess:
        def __init__(self, pid, rss, children=()):
            self.pid = pid
            self._rss = rss
            self._children = list(children)

        def memory_info(self):
            return SimpleNamespace(rss=self._rss)

        def children(self, recursive=True):
            assert recursive is True
            return self._children

    root = _FakeProcess(10, 4 * 1024 * 1024)
    child = _FakeProcess(11, 7 * 1024 * 1024)
    root._children = [child]
    fake_psutil = SimpleNamespace(Process=lambda pid: root if pid == 10 else child)
    monkeypatch.setattr(sandbox, 'psutil', fake_psutil, raising=False)

    memory_kb, process_count = sandbox._process_tree_usage(10)

    assert memory_kb == 11 * 1024
    assert process_count == 2


def test_memory_monitor_kills_when_child_process_count_exceeds_limit(monkeypatch):
    class _FakeProcess:
        pid = 10

        def memory_info(self):
            return SimpleNamespace(rss=1024)

        def children(self, recursive=True):
            return [SimpleNamespace(pid=11, memory_info=lambda: SimpleNamespace(rss=1024))]

    events = []
    monitor = sandbox._MemoryMonitor(10, 64, lambda: events.append('limit'), max_processes=1)
    monkeypatch.setattr(sandbox, 'psutil', SimpleNamespace(Process=lambda _pid: _FakeProcess()))
    monkeypatch.setattr(sandbox, 'time', SimpleNamespace(sleep=lambda _seconds: None))
    monitor._running = True

    monitor._run()

    assert monitor.max_process_count == 2
    assert monitor.killed_due_to_process_limit is True
    assert events == ['limit']


def test_assignment_failure_terminates_and_fails_closed(monkeypatch):
    class _JobApi:
        def AssignProcessToJobObject(self, _job, _process):
            raise RuntimeError('assignment denied')

    terminated = []
    monkeypatch.setattr(sandbox, 'win32job', _JobApi(), raising=False)
    monkeypatch.setattr(
        sandbox,
        '_terminate_sandbox_process',
        lambda job, process, pid=None: terminated.append((job, process, pid)),
    )

    with pytest.raises(sandbox.SandboxError, match='AssignProcessToJobObject'):
        sandbox._assign_process_to_job_object('job', 'process', pid=42)

    assert terminated == [('job', 'process', 42)]


def test_job_list_spawn_does_not_repeat_assignment(monkeypatch):
    class _JobApi:
        def AssignProcessToJobObject(self, _job, _process):
            raise AssertionError('a process created with JOB_LIST must not be reassigned')

    monkeypatch.setattr(sandbox, 'win32job', _JobApi(), raising=False)

    sandbox._assign_process_to_job_object('job', 'process', assigned_at_creation=True)


def test_process_tree_cleanup_kills_descendants_before_root(monkeypatch):
    killed = []

    class _FakeProcess:
        def __init__(self, pid):
            self.pid = pid

        def children(self, recursive=True):
            assert recursive is True
            return [_FakeProcess(11), _FakeProcess(12)]

        def kill(self):
            killed.append(self.pid)

    monkeypatch.setattr(sandbox, 'psutil', SimpleNamespace(Process=_FakeProcess), raising=False)

    sandbox._terminate_process_tree(10)

    assert killed == [12, 11]


def test_host_guard_reservations_bound_concurrent_memory_and_processes():
    guard = HostCapacityGuard(
        max_cpu_percent=90,
        min_available_memory_mb=256,
        reserved_memory_budget_mb=512,
        reserved_process_budget=2,
    )

    first = guard.reserve(memory_mb=384, processes=1)
    second = guard.reserve(memory_mb=256, processes=1)
    assert guard.reserved_memory_mb == 384
    assert guard.reserved_processes == 1
    guard.release(first)
    third = guard.reserve(memory_mb=256, processes=1)

    assert first is not None
    assert second is None
    assert third is not None
    assert guard.reserved_memory_mb == 256
    assert guard.reserved_processes == 1


def test_host_guard_can_dispatch_accounts_for_existing_reservations():
    class _Provider:
        def sample(self):
            return 10, 1024

    guard = HostCapacityGuard(
        max_cpu_percent=90,
        min_available_memory_mb=256,
        metric_provider=_Provider(),
        reserved_memory_budget_mb=768,
    )
    reservation = guard.reserve(memory_mb=512)

    allowed, reason = guard.can_dispatch(memory_mb=300)

    assert reservation is not None
    assert allowed is False
    assert reason == 'reserved judge memory budget is exhausted'


def test_host_guard_rejects_request_that_would_consume_host_reserve():
    class _Provider:
        def sample(self):
            return 10, 1024

    guard = HostCapacityGuard(
        max_cpu_percent=90,
        min_available_memory_mb=256,
        metric_provider=_Provider(),
        reserved_memory_budget_mb=2048,
    )

    allowed, reason = guard.can_dispatch(memory_mb=800)

    assert allowed is False
    assert reason == 'host memory reserve would be exhausted'
