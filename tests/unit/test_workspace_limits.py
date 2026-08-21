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
