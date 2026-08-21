import pytest


def _calculate_judge_workers():
    try:
        from app.config import calculate_judge_workers
    except ImportError as exc:
        pytest.fail(f'worker calculation is not implemented yet: {exc}')
    return calculate_judge_workers


@pytest.mark.parametrize(
    ('cpu_count', 'cap', 'expected'),
    [
        (1, 4, 1),
        (2, 4, 1),
        (4, 4, 2),
        (8, 4, 4),
        (32, 4, 4),
        (32, 2, 2),
    ],
)
def test_worker_count_uses_at_most_half_the_host_and_obeys_cap(cpu_count, cap, expected):
    calculate = _calculate_judge_workers()

    assert calculate(cpu_count, cap) == expected


def test_worker_count_never_returns_zero_or_negative():
    calculate = _calculate_judge_workers()

    assert calculate(0, 8) == 1
    assert calculate(4, 0) == 1


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
