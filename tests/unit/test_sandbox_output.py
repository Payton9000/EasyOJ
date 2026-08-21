from app.judge import sandbox


def test_output_reader_drains_pipe_after_truncation(monkeypatch):
    chunks = [b'123456', b'noise-after-limit', b'']

    def read_file(_handle, _size):
        return 0, chunks.pop(0)

    monkeypatch.setattr(sandbox.win32file, 'ReadFile', read_file)
    captured = {}
    sandbox._read_handle('fake', 5, captured, 'stdout')

    assert captured['stdout'] == (b'12345', True)
    assert chunks == []
