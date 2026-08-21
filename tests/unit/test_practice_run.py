from app.judge.practice import PracticeRunResult
from app.judge.practice import PracticeRunService


def test_practice_run_rejects_input_over_32_kib(app):
    service = PracticeRunService(app)

    result = service.validate_request('python', 'print(1)', 'x' * (32 * 1024 + 1))

    assert result == PracticeRunResult('Invalid', '', 'Custom input exceeds 32KB limit', 0, 0)


def test_practice_run_returns_busy_without_waiting_for_another_run(app):
    service = PracticeRunService(app)
    service._semaphore.acquire()
    try:
        result = service.try_acquire()
    finally:
        service._semaphore.release()

    assert result == PracticeRunResult('Busy', '', 'A custom run is already in progress', 0, 0)


def test_practice_run_validation_accepts_supported_code(app):
    service = PracticeRunService(app)

    result = service.validate_request('python', 'print(1)', '1\n')

    assert result is None


def test_practice_run_pauses_before_execution_when_host_is_under_pressure(app):
    service = PracticeRunService(app)
    service.host_guard = type(
        'BusyGuard',
        (),
        {'can_dispatch': lambda self: (False, 'host available memory is low')},
    )()

    result = service.run(
        type('Problem', (), {'time_limit': 1000, 'memory_limit': 64})(),
        'python',
        'print(1)',
        '',
    )

    assert result.status == 'Busy'
    assert result.error == 'Host is busy: host available memory is low'
