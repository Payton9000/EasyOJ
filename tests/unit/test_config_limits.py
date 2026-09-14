import pytest

from app.config import calculate_judge_workers
from app.config import host_cpu_limit
from app.config import judge_worker_limits


@pytest.mark.parametrize(
    ('cpu_count', 'cap', 'expected'),
    [
        (1, None, 1),
        (2, None, 2),
        (4, None, 4),
        (8, None, 8),
        (16, None, 16),
        (32, None, 32),
        (32, 2, 2),
        (8, 4, 4),
    ],
)
def test_worker_count_defaults_to_logical_cpus_and_optional_cap(cpu_count, cap, expected):
    if cap is None:
        assert calculate_judge_workers(cpu_count) == expected
    else:
        assert calculate_judge_workers(cpu_count, cap) == expected


def test_worker_count_never_returns_zero_or_negative():
    assert calculate_judge_workers(0) == 1
    assert calculate_judge_workers(0, 8) == 1
    assert calculate_judge_workers(4, 0) == 1


def test_config_workers_follow_host_cpus_without_a_hard_four_cap():
    workers, cap = judge_worker_limits(cpu_count=16, environ={})
    assert workers == 16
    assert cap == 16


def test_config_honors_operator_worker_overrides_above_four():
    workers, cap = judge_worker_limits(
        cpu_count=4,
        environ={'MAX_JUDGE_WORKERS': '12', 'JUDGE_WORKER_CAP': '12'},
    )
    assert workers == 12
    assert cap == 12


def test_default_host_cpu_limit_allows_full_machine():
    assert host_cpu_limit(environ={}) == 100
    assert host_cpu_limit(environ={'JUDGE_HOST_MAX_CPU_PERCENT': '70'}) == 70


def test_python_toolchain_prefers_project_local_runtime(tmp_path):
    from app.config import _find_python_exe

    local_python = tmp_path / '.venv' / 'Scripts' / 'python.exe'
    local_python.parent.mkdir(parents=True)
    local_python.write_bytes(b'python')

    assert _find_python_exe(str(tmp_path)) == str(local_python)


def test_production_rejects_missing_or_placeholder_secret(monkeypatch):
    from flask import Flask

    from app.config import ProductionConfig

    app = Flask('test')
    monkeypatch.setenv('SECRET_KEY', 'change-me-to-a-random-string')
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        ProductionConfig.init_app(app)

    monkeypatch.setenv('SECRET_KEY', 'too-short')
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        ProductionConfig.init_app(app)


def test_request_cap_allows_a_full_size_testcase_pair():
    """MAX_CONTENT_LENGTH must clear both testcase limits plus multipart framing.

    It defaulted to 256 KB while the testcase limits allowed 4 MB each, so Flask
    aborted the request with 413 before the view ran and the documented limits
    were unreachable.
    """
    from app.config import Config
    from app.config import DevelopmentConfig
    from app.config import ProductionConfig
    from app.config import TestingConfig

    for config_cls in (Config, DevelopmentConfig, ProductionConfig, TestingConfig):
        pair_bytes = config_cls.TESTCASE_MAX_INPUT_BYTES + config_cls.TESTCASE_MAX_OUTPUT_BYTES
        assert config_cls.MAX_CONTENT_LENGTH >= pair_bytes, (
            f'{config_cls.__name__}: cap {config_cls.MAX_CONTENT_LENGTH} '
            f'rejects an allowed {pair_bytes}-byte pair'
        )


def test_deployment_defaults_do_not_pin_a_too_small_request_cap():
    from scripts.deploy.windows import deploy_core

    assert 'MAX_CONTENT_LENGTH' not in deploy_core.MANAGED_ENV_DEFAULTS


def test_default_configuration_is_not_debug():
    """An unnamed configuration must never enable the Werkzeug debugger.

    'default' used to resolve to DevelopmentConfig, so any caller that omitted a
    name got DEBUG=True — remote code execution if it was ever reachable.
    """
    from app.config import config

    assert config['default'].DEBUG is False
    assert config['default'] is config['production']


def test_backup_settings_are_bounded():
    from app.config import Config

    assert Config.BACKUP_KEEP >= 1
    assert Config.BACKUP_INTERVAL_SECONDS >= 600
    assert Config.BACKUP_DIR.endswith('backups')


def test_testing_configuration_disables_backups():
    """Tests must not spawn a backup thread or write files."""
    from app.config import TestingConfig

    assert TestingConfig.BACKUP_ENABLED is False
