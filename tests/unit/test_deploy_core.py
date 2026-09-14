from pathlib import Path

import pytest

from scripts.deploy.windows.deploy_core import build_local_toolchain_paths
from scripts.deploy.windows.deploy_core import ensure_project_layout
from scripts.deploy.windows.deploy_core import generate_env_file
from scripts.deploy.windows.deploy_core import resolve_project_root
from scripts.deploy.windows.deploy_gui import DeploymentError
from scripts.deploy.windows.deploy_gui import run_server
from scripts.deploy.windows.deploy_gui import run_step


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / 'run.py').write_text('', encoding='utf-8')
    (tmp_path / 'app').mkdir()
    return tmp_path


def test_resolve_project_root_requires_easyoj_markers(project_root):
    assert resolve_project_root(project_root) == project_root.resolve()

    with pytest.raises(ValueError):
        resolve_project_root(project_root / 'missing')


def test_ensure_layout_creates_only_project_owned_directories(project_root):
    paths = ensure_project_layout(project_root)

    assert paths.root == project_root.resolve()
    assert paths.data_dir == (project_root / 'data').resolve()
    assert paths.toolchain_dir == (project_root / 'toolchain').resolve()
    for directory in (paths.data_dir, paths.judge_log_dir, paths.submission_dir):
        assert directory.is_dir()


def test_generate_env_preserves_existing_secret_and_uses_bounded_defaults(project_root):
    env_path = project_root / '.env'
    env_path.write_text(f"SECRET_KEY={'k' * 64}\nMAX_JUDGE_WORKERS=99\n", encoding='utf-8')

    generate_env_file(project_root, env_path=env_path)
    content = env_path.read_text(encoding='utf-8')

    assert f"SECRET_KEY={'k' * 64}" in content
    assert 'MAX_JUDGE_WORKERS=' not in content
    assert 'JUDGE_WORKER_CAP=' not in content
    assert 'JUDGE_REQUIRE_SANDBOX=1' in content


def test_generate_env_replaces_placeholder_secret(project_root):
    env_path = project_root / '.env'
    env_path.write_text('SECRET_KEY=change-me-to-a-random-string\n', encoding='utf-8')

    generate_env_file(project_root, env_path=env_path)

    secret_line = next(
        line
        for line in env_path.read_text(encoding='utf-8').splitlines()
        if line.startswith('SECRET_KEY=')
    )
    assert len(secret_line.split('=', 1)[1]) >= 32
    assert 'change-me' not in secret_line


def test_local_toolchain_paths_never_escape_project_root(project_root):
    paths = build_local_toolchain_paths(project_root)

    assert set(paths) == {'g++', 'javac', 'java', 'python'}
    assert all(
        Path(path).resolve().is_relative_to(project_root.resolve()) for path in paths.values()
    )


def test_local_python_prefers_embedded_runtime_over_application_venv(project_root):
    runtime_python = project_root / 'runtime' / 'python' / 'python.exe'
    runtime_python.parent.mkdir(parents=True)
    runtime_python.write_bytes(b'python')
    venv_python = project_root / '.venv' / 'Scripts' / 'python.exe'
    venv_python.parent.mkdir(parents=True)
    venv_python.write_bytes(b'python')

    paths = build_local_toolchain_paths(project_root)

    assert Path(paths['python']) == runtime_python.resolve()


def test_deployment_command_does_not_use_shell(tmp_path, monkeypatch):
    captured = {}

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            captured['timeout'] = timeout
            return ('ready\n', None)

    def fake_popen(command, **kwargs):
        captured['command'] = command
        captured['kwargs'] = kwargs
        return FakeProcess()

    monkeypatch.setattr('scripts.deploy.windows.deploy_gui.subprocess.Popen', fake_popen)
    messages = []
    run_step(['powershell.exe', '-NoProfile'], cwd=tmp_path, log=messages.append)

    assert captured['kwargs']['shell'] is False
    assert captured['kwargs']['cwd'] == str(tmp_path)
    assert captured['timeout'] == 3600
    assert 'ready' in messages


def test_run_server_rejects_duplicate_port(project_root, monkeypatch):
    python_path = project_root / '.venv' / 'Scripts' / 'python.exe'
    python_path.parent.mkdir(parents=True)
    python_path.write_bytes(b'python')
    monkeypatch.setattr('scripts.deploy.windows.deploy_gui._port_is_open', lambda port: True)

    def unexpected_popen(*args, **kwargs):
        raise AssertionError('must not start a second server')

    monkeypatch.setattr('scripts.deploy.windows.deploy_gui.subprocess.Popen', unexpected_popen)
    with pytest.raises(DeploymentError, match='already in use'):
        run_server(project_root, lambda message: None)


def test_run_server_waits_for_health_check(project_root, monkeypatch):
    python_path = project_root / '.venv' / 'Scripts' / 'python.exe'
    python_path.parent.mkdir(parents=True)
    python_path.write_bytes(b'python')
    captured = {}

    class FakeProcess:
        pid = 1234

        def poll(self):
            return None

    def fake_popen(command, **kwargs):
        captured['command'] = command
        return FakeProcess()

    monkeypatch.setattr('scripts.deploy.windows.deploy_gui._port_is_open', lambda port: False)
    monkeypatch.setattr('scripts.deploy.windows.deploy_gui._wait_for_server', lambda port: True)
    monkeypatch.setattr('scripts.deploy.windows.deploy_gui.subprocess.Popen', fake_popen)
    messages = []

    run_server(project_root, messages.append)

    assert captured['command'][-2:] == ['run.py', 'production']
    assert any('PID 1234' in message for message in messages)
