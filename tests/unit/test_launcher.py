"""The double-click entry point is the only thing a teacher has to understand."""

import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

launcher = pytest.importorskip('launcher')


def test_batch_entry_points_exist_at_the_project_root():
    """They must sit at the top level: that is where a teacher looks."""
    names = {path.name for path in REPO_ROOT.glob('*.bat')}
    assert any('EasyOJ' in name for name in names), names


def test_batch_files_are_ascii_only():
    """A UTF-8 batch file plus chcp 65001 makes cmd mis-parse its own lines.

    That produced errors such as "'_PY' is not recognized" on a real run, so all
    user-facing Chinese lives in the Python launcher instead.
    """
    for path in REPO_ROOT.glob('*.bat'):
        content = path.read_bytes()
        non_ascii = [byte for byte in content if byte > 127]
        assert not non_ascii, f'{path.name} contains {len(non_ascii)} non-ASCII bytes'


def test_batch_files_quote_paths_with_spaces():
    """The project folder may contain spaces; unquoted %~dp0 would break."""
    for path in REPO_ROOT.glob('*.bat'):
        text = path.read_text(encoding='ascii')
        assert '"%~dp0scripts\\launcher.py"' in text or 'launcher.py' not in text
        assert 'cd /d "%~dp0"' in text


def test_launcher_points_at_the_shared_service_script():
    assert launcher.SERVICE_SCRIPT == REPO_ROOT / 'scripts' / 'start_service.py'
    assert launcher.SERVICE_SCRIPT.is_file()


def test_port_comes_from_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, 'PROJECT_ROOT', tmp_path)
    monkeypatch.delenv('EASYOJ_PORT', raising=False)
    (tmp_path / '.env').write_text('EASYOJ_HOST=0.0.0.0\nEASYOJ_PORT=5150\n', encoding='utf-8')

    assert launcher._configured_port() == 5150


def test_invalid_port_falls_back_instead_of_crashing(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, 'PROJECT_ROOT', tmp_path)
    monkeypatch.delenv('EASYOJ_PORT', raising=False)
    (tmp_path / '.env').write_text('EASYOJ_PORT=not-a-number\n', encoding='utf-8')

    assert launcher._configured_port() == 5000


def test_missing_setup_script_is_reported_without_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(launcher, 'VENV_PYTHON', tmp_path / 'absent' / 'python.exe')
    monkeypatch.setattr(launcher, 'BOOTSTRAP', tmp_path / 'absent' / 'bootstrap.ps1')

    assert launcher.ensure_environment() is False
    assert 'Setup script is missing' in capsys.readouterr().out


def test_missing_python_gives_install_instructions(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(launcher, 'VENV_PYTHON', tmp_path / 'absent' / 'python.exe')
    monkeypatch.setattr(launcher, 'BOOTSTRAP', tmp_path / 'bootstrap.ps1')
    (tmp_path / 'bootstrap.ps1').write_text('# stub', encoding='utf-8')
    monkeypatch.setattr(launcher, '_system_python', lambda: None)

    assert launcher.ensure_environment() is False
    output = capsys.readouterr().out
    assert 'python.org' in output
    assert 'Add python.exe to PATH' in output


def test_ensure_environment_uses_a_long_bootstrap_timeout(tmp_path, monkeypatch):
    """GitHub-sized compiler zips exceed one hour on a ~40KB/s classroom link."""
    monkeypatch.setattr(launcher, 'VENV_PYTHON', tmp_path / 'absent' / 'python.exe')
    monkeypatch.setattr(launcher, 'BOOTSTRAP', tmp_path / 'bootstrap.ps1')
    (tmp_path / 'bootstrap.ps1').write_text('# stub', encoding='utf-8')
    monkeypatch.setattr(launcher, '_system_python', lambda: ['py', '-3'])
    captured = {}

    def fake_run(command, *, timeout=3600, env=None):
        captured['timeout'] = timeout
        captured['command'] = command
        return 1

    monkeypatch.setattr(launcher, '_run', fake_run)
    assert launcher.ensure_environment() is False
    assert captured['timeout'] >= 10800


def test_ensure_environment_reruns_bootstrap_when_venv_exists_without_compilers(
    tmp_path, monkeypatch
):
    venv_python = tmp_path / '.venv' / 'Scripts' / 'python.exe'
    venv_python.parent.mkdir(parents=True)
    venv_python.write_bytes(b'python')
    monkeypatch.setattr(launcher, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(launcher, 'VENV_PYTHON', venv_python)
    monkeypatch.setattr(launcher, 'BOOTSTRAP', tmp_path / 'bootstrap.ps1')
    (tmp_path / 'bootstrap.ps1').write_text('# stub', encoding='utf-8')
    captured = {}

    def fake_run(command, *, timeout=3600, env=None):
        captured['called'] = True
        return 1

    monkeypatch.setattr(launcher, '_run', fake_run)
    assert launcher.ensure_environment() is False
    assert captured.get('called') is True


def test_stop_reports_when_nothing_is_running(capsys):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        free_port = probe.getsockname()[1]

    assert launcher.stop_service(free_port) is True
    assert 'not running' in capsys.readouterr().out


def test_start_does_not_treat_a_foreign_listener_as_this_install(monkeypatch):
    """Another EasyOJ on :5000 must not skip first-run setup for a new folder."""
    ports = {'value': 5000}
    monkeypatch.setattr(launcher, '_configured_port', lambda: ports['value'])
    monkeypatch.setattr(launcher, '_port_in_use', lambda port: port == 5000)
    monkeypatch.setattr(launcher, '_is_this_checkout_listening', lambda port: False)
    called = {}
    monkeypatch.setattr(
        launcher, 'ensure_environment', lambda: called.setdefault('env', True) or True
    )

    def fake_configuration():
        ports['value'] = 5001
        called['cfg'] = True
        return True

    monkeypatch.setattr(launcher, 'ensure_configuration', fake_configuration)
    monkeypatch.setattr(
        launcher,
        'start_service',
        lambda port, open_browser=True: called.setdefault('start_port', port) or True,
    )

    assert launcher.main(['start', '--no-browser']) == 0
    assert called['env'] is True
    assert called['cfg'] is True
    assert called['start_port'] == 5001


def test_start_rereads_port_after_the_setup_wizard(monkeypatch):
    ports = {'value': 5000}

    monkeypatch.setattr(launcher, '_configured_port', lambda: ports['value'])
    monkeypatch.setattr(launcher, '_port_in_use', lambda port: False)
    monkeypatch.setattr(launcher, '_is_this_checkout_listening', lambda port: False)
    monkeypatch.setattr(launcher, 'ensure_environment', lambda: True)

    def fake_configuration():
        ports['value'] = 5001
        return True

    started = {}
    monkeypatch.setattr(launcher, 'ensure_configuration', fake_configuration)
    monkeypatch.setattr(
        launcher,
        'start_service',
        lambda port, open_browser=True: started.setdefault('port', port) or True,
    )

    assert launcher.main(['start', '--no-browser']) == 0
    assert started['port'] == 5001


def test_start_exits_when_this_checkout_is_already_listening(monkeypatch, capsys):
    monkeypatch.setattr(launcher, '_configured_port', lambda: 5000)
    monkeypatch.setattr(launcher, '_is_this_checkout_listening', lambda port: True)

    def must_not_setup():
        raise AssertionError('must not run setup for an already-running checkout')

    monkeypatch.setattr(launcher, 'ensure_environment', must_not_setup)
    monkeypatch.setattr(
        launcher, 'webbrowser', type('W', (), {'open': staticmethod(lambda url: None)})
    )

    assert launcher.main(['start', '--no-browser']) == 0
    assert 'already running' in capsys.readouterr().out


def test_toolchain_script_next_step_uses_this_project_root():
    script = Path('scripts/deploy/windows/setup_toolchain.ps1').read_text(encoding='utf-8')
    assert 'd:/EasyOJ/.venv' not in script
    assert 'Join-Path $root' in script or '.venv\\Scripts\\python.exe' in script
