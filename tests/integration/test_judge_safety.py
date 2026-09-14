from app.judge.executor import Executor


def test_sandbox_enabled_host_without_support_fails_closed(app, monkeypatch, tmp_path):
    app.config.update(
        {
            'SANDBOX_ENABLED': True,
            'JUDGE_REQUIRE_SANDBOX': True,
            'COMPILER_PATHS': {'python': 'python'},
        }
    )
    monkeypatch.setattr('app.judge.sandbox.is_supported', lambda: False)

    result = Executor(app).execute(str(tmp_path), 'python', '', 100, 16)

    assert result['status'] == 'SystemError'
    assert 'sandbox' in result['error'].lower()
