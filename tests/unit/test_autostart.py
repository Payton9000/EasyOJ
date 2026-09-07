"""Automatic startup must be installable by a teacher with no admin rights."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DIR = REPO_ROOT / 'scripts' / 'deploy' / 'windows'
if str(DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(DEPLOY_DIR))

autostart = pytest.importorskip('autostart')


def test_launcher_prefers_pythonw_so_no_console_appears():
    """A console window flashing up at every sign-in would look like a fault."""
    interpreter, script = autostart.launcher_command(REPO_ROOT)

    assert interpreter.name.lower() in {'pythonw.exe', 'python.exe'}
    assert interpreter.is_file()
    assert script == REPO_ROOT / 'scripts' / 'start_service.py'
    assert script.is_file()


def test_launcher_rejects_a_project_without_the_service_script(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart, 'resolve_project_root', lambda value: Path(value))
    (tmp_path / '.venv' / 'Scripts').mkdir(parents=True)
    (tmp_path / '.venv' / 'Scripts' / 'python.exe').write_bytes(b'')

    with pytest.raises(RuntimeError, match='Missing service launcher'):
        autostart.launcher_command(tmp_path)


def test_shortcut_install_status_and_removal_round_trip(tmp_path, monkeypatch):
    """Install, observe, remove: the state a teacher toggles from the GUI."""
    fake_startup = tmp_path / 'Startup'
    fake_startup.mkdir()
    monkeypatch.setattr(autostart, 'startup_folder', lambda: fake_startup)
    # Keep the probe away from the real Task Scheduler.
    monkeypatch.setattr(autostart, '_task_exists', lambda: False)

    assert autostart.status(REPO_ROOT).installed is False

    result = autostart.install_shortcut(REPO_ROOT)
    assert result.installed is True
    assert result.method == 'startup-folder'
    shortcut = fake_startup / autostart.SHORTCUT_NAME
    assert shortcut.is_file()

    current = autostart.status(REPO_ROOT)
    assert current.installed is True
    assert current.method == 'startup-folder'

    assert autostart.remove_shortcut() is True
    assert not shortcut.exists()
    assert autostart.status(REPO_ROOT).installed is False
    # Removing twice must be harmless: the GUI button can be pressed again.
    assert autostart.remove_shortcut() is False


def test_shortcut_points_at_this_project(tmp_path, monkeypatch):
    fake_startup = tmp_path / 'Startup'
    fake_startup.mkdir()
    monkeypatch.setattr(autostart, 'startup_folder', lambda: fake_startup)
    autostart.install_shortcut(REPO_ROOT)

    win32com = pytest.importorskip('win32com.client')
    shell = win32com.Dispatch('WScript.Shell')
    link = shell.CreateShortCut(str(fake_startup / autostart.SHORTCUT_NAME))

    assert Path(link.TargetPath).is_file()
    assert 'start_service.py' in link.Arguments
    assert Path(link.WorkingDirectory) == REPO_ROOT
    autostart.remove_shortcut()


def test_disable_reports_each_mechanism_it_removed(tmp_path, monkeypatch):
    fake_startup = tmp_path / 'Startup'
    fake_startup.mkdir()
    monkeypatch.setattr(autostart, 'startup_folder', lambda: fake_startup)
    monkeypatch.setattr(autostart, 'remove_task', lambda: False)
    autostart.install_shortcut(REPO_ROOT)

    removed = autostart.disable(REPO_ROOT)

    assert removed == ['startup-folder']
    assert autostart.disable(REPO_ROOT) == []


def test_scheduled_task_failure_is_reported_not_raised_raw(monkeypatch):
    """Without elevation schtasks denies access; the message must stay actionable."""

    class _Denied:
        returncode = 1
        stdout = ''
        stderr = 'ERROR: Access is denied.'

    monkeypatch.setattr(autostart, '_run_schtasks', lambda arguments: _Denied())

    with pytest.raises(RuntimeError, match='Access is denied'):
        autostart.install_task(REPO_ROOT)
