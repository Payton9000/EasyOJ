from threading import Event


def test_workspace_usage_detects_size_and_file_count(tmp_path):
    from app.judge.sandbox import _workspace_usage

    (tmp_path / 'one.txt').write_bytes(b'x' * 11)
    (tmp_path / 'nested').mkdir()
    (tmp_path / 'nested' / 'two.txt').write_bytes(b'y' * 7)

    size, files, exceeded = _workspace_usage(str(tmp_path), max_bytes=10, max_files=8)

    assert size >= 11
    assert files >= 1
    assert exceeded is True


def test_vanishing_file_is_not_a_limit_violation(tmp_path, monkeypatch):
    """A file removed between listing and stat must not fail the submission.

    Compilers create and delete temporaries constantly. Treating every OSError as
    a violation reported "workspace limit exceeded" on ordinary submissions.
    """
    import os

    from app.judge import sandbox

    (tmp_path / 'kept.txt').write_bytes(b'x' * 4)
    (tmp_path / 'gone.txt').write_bytes(b'y' * 4)

    real_stat = os.stat

    def flaky_stat(path, *args, **kwargs):
        if str(path).endswith('gone.txt'):
            raise FileNotFoundError(path)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(sandbox.os, 'stat', flaky_stat)

    size, files, exceeded = sandbox._workspace_usage(str(tmp_path), max_bytes=1024, max_files=8)

    assert exceeded is False
    assert files == 1
    assert size == 4


def test_judge_supplied_stdin_file_is_not_counted(tmp_path):
    from app.judge import sandbox

    (tmp_path / sandbox._STDIN_FILENAME).write_bytes(b'z' * 4096)

    size, files, exceeded = sandbox._workspace_usage(str(tmp_path), max_bytes=64, max_files=4)

    assert (size, files, exceeded) == (0, 0, False)


def test_workspace_monitor_calls_limit_callback(tmp_path):
    from app.judge.sandbox import _WorkspaceMonitor

    (tmp_path / 'output.bin').write_bytes(b'x' * 32)
    limited = Event()
    monitor = _WorkspaceMonitor(
        str(tmp_path), max_bytes=16, max_files=8, on_limit=limited.set, interval=0.01
    )

    monitor.start()
    try:
        assert limited.wait(1)
        assert monitor.killed_due_to_limit is True
    finally:
        monitor.stop()
