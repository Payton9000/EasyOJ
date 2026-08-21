from app.judge.engine import _JudgeExecutionService


def test_deterministic_missing_test_data_is_not_retried():
    service = _JudgeExecutionService(app=None, max_retries=2, log_dir=None)

    assert service.should_retry('Failed', 'No test cases') is False
    assert service.should_retry('SystemError', 'worker setup failed') is True
