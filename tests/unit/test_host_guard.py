from app.judge.host_guard import HostCapacityGuard


class _MetricProvider:
    def __init__(self, values=None, error=None):
        self.values = values or (10.0, 4096)
        self.error = error
        self.calls = 0

    def sample(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.values


def test_host_guard_accepts_healthy_cpu_and_memory():
    guard = HostCapacityGuard(
        max_cpu_percent=85,
        min_available_memory_mb=1024,
        metric_provider=_MetricProvider((42.5, 4096)),
    )

    assert guard.can_dispatch() == (True, '')
    assert guard.latest_snapshot.cpu_percent == 42.5
    assert guard.latest_snapshot.available_memory_mb == 4096


def test_host_guard_pauses_when_cpu_is_above_threshold():
    guard = HostCapacityGuard(85, 1024, metric_provider=_MetricProvider((90.0, 4096)))

    allowed, reason = guard.can_dispatch()

    assert allowed is False
    assert reason == 'host CPU usage is 90.0% (limit 85%)'


def test_host_guard_does_not_pause_for_cpu_when_limit_is_100():
    guard = HostCapacityGuard(100, 1024, metric_provider=_MetricProvider((100.0, 4096)))

    assert guard.can_dispatch() == (True, '')

    saturated = HostCapacityGuard(100, 1024, metric_provider=_MetricProvider((110.0, 4096)))
    assert saturated.can_dispatch() == (True, '')


def test_host_guard_pauses_when_available_memory_is_below_reserve():
    guard = HostCapacityGuard(85, 1024, metric_provider=_MetricProvider((20.0, 512)))

    allowed, reason = guard.can_dispatch()

    assert allowed is False
    assert reason == 'host available memory is 512 MiB (minimum 1024 MiB)'


def test_host_guard_pauses_if_metrics_cannot_be_sampled():
    guard = HostCapacityGuard(
        85,
        1024,
        metric_provider=_MetricProvider(error=RuntimeError('sensor failed')),
    )

    allowed, reason = guard.can_dispatch()

    assert allowed is False
    assert reason == 'host metrics unavailable'
    assert guard.latest_snapshot is None


def test_host_guard_reuses_a_recent_snapshot():
    provider = _MetricProvider((20.0, 4096))
    times = iter((10.0, 10.1, 11.5))
    guard = HostCapacityGuard(
        85,
        1024,
        metric_provider=provider,
        sample_ttl_seconds=1.0,
        clock=lambda: next(times),
    )

    assert guard.can_dispatch()[0] is True
    assert guard.can_dispatch()[0] is True
    assert provider.calls == 1
    assert guard.can_dispatch()[0] is True
    assert provider.calls == 2
