import importlib

import pytest


def _policy_class():
    try:
        return importlib.import_module('app.judge.policy').JudgePolicy
    except (ImportError, AttributeError) as exc:
        pytest.fail(f'judge policy is not implemented yet: {exc}')


def test_policy_caps_workers_and_limits():
    JudgePolicy = _policy_class()

    policy = JudgePolicy.from_config(
        {
            'MAX_JUDGE_WORKERS': 32,
            'JUDGE_WORKER_CAP': 8,
            'JUDGE_QUEUE_MAXSIZE': 200,
            'MAX_TIME_LIMIT_MS': 20000,
            'MAX_MEMORY_LIMIT_MB': 512,
            'MAX_OUTPUT_SIZE': 65536,
            'SANDBOX_ENABLED': True,
            'JUDGE_REQUIRE_SANDBOX': False,
        }
    )

    assert policy.max_workers == 8
    assert policy.max_time_limit_ms == 20000
    assert policy.max_memory_limit_mb == 512
    assert policy.max_output_size == 65536


def test_policy_fails_closed_when_required_sandbox_is_disabled():
    JudgePolicy = _policy_class()

    with pytest.raises(ValueError, match='sandbox'):
        JudgePolicy.from_config(
            {
                'SANDBOX_ENABLED': False,
                'JUDGE_REQUIRE_SANDBOX': True,
            }
        )


def test_policy_requires_appcontainer_in_strict_production_mode():
    JudgePolicy = _policy_class()

    with pytest.raises(ValueError, match='AppContainer'):
        JudgePolicy.from_config(
            {
                'SANDBOX_ENABLED': True,
                'JUDGE_REQUIRE_SANDBOX': True,
                'SANDBOX_APP_CONTAINER': False,
                'SANDBOX_STRICT_APP_CONTAINER': True,
            }
        )


def test_policy_clamps_invalid_limits_to_safe_values():
    JudgePolicy = _policy_class()

    policy = JudgePolicy.from_config(
        {
            'MAX_JUDGE_WORKERS': 0,
            'JUDGE_WORKER_CAP': 0,
            'JUDGE_QUEUE_MAXSIZE': 0,
            'MAX_TIME_LIMIT_MS': 0,
            'MAX_MEMORY_LIMIT_MB': 0,
            'MAX_OUTPUT_SIZE': 0,
            'SANDBOX_ENABLED': True,
            'JUDGE_REQUIRE_SANDBOX': False,
        }
    )

    assert policy.max_workers == 1
    assert policy.queue_maxsize == 1
    assert policy.max_time_limit_ms == 1
    assert policy.max_memory_limit_mb == 1
    assert policy.max_output_size == 1


def test_policy_caps_operator_overrides_to_machine_safe_bounds():
    JudgePolicy = _policy_class()

    policy = JudgePolicy.from_config(
        {
            'MAX_JUDGE_WORKERS': 64,
            'JUDGE_WORKER_CAP': 64,
            'JUDGE_QUEUE_MAXSIZE': 999999,
            'MAX_TIME_LIMIT_MS': 999999,
            'MAX_MEMORY_LIMIT_MB': 999999,
            'MAX_OUTPUT_SIZE': 999999999,
            'SANDBOX_MAX_PROCESSES': 999,
            'SANDBOX_ENABLED': True,
            'JUDGE_REQUIRE_SANDBOX': False,
        }
    )

    assert policy.queue_maxsize == 10000
    assert policy.max_time_limit_ms == 120000
    assert policy.max_memory_limit_mb == 2048
    assert policy.max_output_size == 4 * 1024 * 1024
    assert policy.max_processes == 32


def test_engine_uses_policy_worker_cap(app):
    from app.judge.engine import JudgeEngine

    app.config.update(
        {
            'MAX_JUDGE_WORKERS': 32,
            'JUDGE_WORKER_CAP': 2,
            'JUDGE_REQUIRE_SANDBOX': False,
        }
    )
    engine = JudgeEngine(app, config_name='testing')

    assert engine.max_workers == 2
