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


def test_stop_reports_when_nothing_is_running(capsys):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        free_port = probe.getsockname()[1]

    assert launcher.stop_service(free_port) is True
    assert 'not running' in capsys.readouterr().out
