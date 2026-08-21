from types import SimpleNamespace

from app.judge.engine import JudgeEngine


def test_start_is_idempotent_when_engine_is_already_running(app, monkeypatch):
    engine = JudgeEngine(app, config_name='testing')
    sentinel_worker = SimpleNamespace(is_alive=lambda: True)
    engine.is_running = True
    engine.workers = [sentinel_worker]

    def fail_if_spawned(*args, **kwargs):
        raise AssertionError('a second worker set must not be spawned')

    monkeypatch.setattr(engine.mp_ctx, 'Process', fail_if_spawned)

    assert engine.start() is False
    assert engine.workers == [sentinel_worker]


def test_stop_clears_workers_that_have_exited(app):
    engine = JudgeEngine(app, config_name='testing')

    class StoppedWorker:
        def __init__(self):
            self.joined = False

        def join(self, timeout=None):
            self.joined = True

        def is_alive(self):
            return False

    worker = StoppedWorker()
    engine.is_running = True
    engine.workers = [worker]

    assert engine.stop() is True
    assert worker.joined is True
    assert engine.workers == []


def test_dispatch_interval_uses_bounded_host_backoff_config(app, monkeypatch):
    monkeypatch.setitem(app.config, 'JUDGE_HOST_BACKOFF_MS', 250)

    engine = JudgeEngine(app, config_name='testing')

    assert engine.dispatch_interval_seconds == 0.25
