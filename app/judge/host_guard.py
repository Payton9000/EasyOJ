import threading
import time
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class HostSnapshot:
    cpu_percent: float
    available_memory_mb: int


@dataclass(frozen=True)
class ResourceReservation:
    memory_mb: int
    processes: int


class _PsutilMetricProvider:
    """Sample host load without blocking the caller.

    ``cpu_percent(interval=0.1)`` sleeps for 100 ms on every expired sample, which
    the dispatcher paid on each tick and every practice run paid inside the web
    request. ``interval=None`` returns the average since the previous call, so a
    warm-up sample is primed once at construction time.
    """

    def __init__(self):
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

    def sample(self):
        cpu_percent = float(psutil.cpu_percent(interval=None))
        available_memory_mb = int(psutil.virtual_memory().available / (1024 * 1024))
        return cpu_percent, available_memory_mb


class HostCapacityGuard:
    def __init__(
        self,
        max_cpu_percent,
        min_available_memory_mb,
        *,
        metric_provider=None,
        sample_ttl_seconds=1.0,
        clock=None,
        reserved_memory_budget_mb=None,
        reserved_process_budget=None,
    ):
        self.max_cpu_percent = float(max_cpu_percent)
        self.min_available_memory_mb = int(min_available_memory_mb)
        self.metric_provider = metric_provider or _PsutilMetricProvider()
        self.sample_ttl_seconds = max(0.0, float(sample_ttl_seconds))
        self.clock = clock or time.monotonic
        self.latest_snapshot = None
        self._sampled_at = None
        self.reserved_memory_budget_mb = (
            None if reserved_memory_budget_mb is None else max(0, int(reserved_memory_budget_mb))
        )
        self.reserved_process_budget = (
            None if reserved_process_budget is None else max(0, int(reserved_process_budget))
        )
        self.reserved_memory_mb = 0
        self.reserved_processes = 0
        self._reservations = []
        self._reservation_lock = threading.RLock()

    def snapshot(self):
        now = self.clock()
        if (
            self.latest_snapshot is not None
            and self._sampled_at is not None
            and now - self._sampled_at <= self.sample_ttl_seconds
        ):
            return self.latest_snapshot

        cpu_percent, available_memory_mb = self.metric_provider.sample()
        self.latest_snapshot = HostSnapshot(float(cpu_percent), int(available_memory_mb))
        self._sampled_at = now
        return self.latest_snapshot

    def can_dispatch(self, memory_mb=0, processes=0):
        requested_memory_mb = max(0, int(memory_mb or 0))
        requested_processes = max(0, int(processes or 0))
        try:
            snapshot = self.snapshot()
        except Exception:
            self.latest_snapshot = None
            self._sampled_at = None
            return False, 'host metrics unavailable'

        # A 100% limit means "do not pause for CPU". Host freeze prevention is
        # below-normal Job Object / worker priority, not leaving cores idle.
        if self.max_cpu_percent < 100 and snapshot.cpu_percent > self.max_cpu_percent:
            return (
                False,
                f'host CPU usage is {snapshot.cpu_percent:.1f}% '
                f'(limit {self.max_cpu_percent:.0f}%)',
            )
        if snapshot.available_memory_mb < self.min_available_memory_mb:
            return (
                False,
                f'host available memory is {snapshot.available_memory_mb} MiB '
                f'(minimum {self.min_available_memory_mb} MiB)',
            )
        with self._reservation_lock:
            projected_memory_mb = self.reserved_memory_mb + requested_memory_mb
            if (
                self.reserved_memory_budget_mb is not None
                and projected_memory_mb > self.reserved_memory_budget_mb
            ):
                return False, 'reserved judge memory budget is exhausted'
            if (
                self.reserved_process_budget is not None
                and self.reserved_processes + requested_processes > self.reserved_process_budget
            ):
                return False, 'reserved judge process budget is exhausted'
            if (
                requested_memory_mb
                and snapshot.available_memory_mb - projected_memory_mb
                < self.min_available_memory_mb
            ):
                return False, 'host memory reserve would be exhausted'
        return True, ''

    def reserve(self, memory_mb, processes=1):
        """Atomically reserve capacity for a sandbox about to be started.

        The reservation is deliberately separate from the host snapshot: the
        snapshot protects against current pressure while this accounting
        prevents concurrent callers from admitting their full limits at once.
        Callers must release the returned token in a ``finally`` block.
        """
        requested_memory_mb = max(0, int(memory_mb or 0))
        requested_processes = max(0, int(processes or 0))
        token = ResourceReservation(requested_memory_mb, requested_processes)
        with self._reservation_lock:
            if (
                self.reserved_memory_budget_mb is not None
                and self.reserved_memory_mb + requested_memory_mb > self.reserved_memory_budget_mb
            ):
                return None
            if (
                self.reserved_process_budget is not None
                and self.reserved_processes + requested_processes > self.reserved_process_budget
            ):
                return None
            self._reservations.append(token)
            self.reserved_memory_mb += requested_memory_mb
            self.reserved_processes += requested_processes
        return token

    def release(self, reservation):
        if not isinstance(reservation, ResourceReservation):
            return
        with self._reservation_lock:
            for index, active in enumerate(self._reservations):
                if active is reservation:
                    del self._reservations[index]
                    break
            else:
                return
            self.reserved_memory_mb = max(0, self.reserved_memory_mb - reservation.memory_mb)
            self.reserved_processes = max(0, self.reserved_processes - reservation.processes)
