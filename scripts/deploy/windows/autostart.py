"""Start EasyOJ automatically when the operator signs in.

A classroom host gets rebooted constantly, and a teacher should not have to
remember to launch anything before first period.

Two mechanisms are supported:

* A shortcut in the per-user Startup folder. This is the default because it needs
  no administrator rights, which ``schtasks`` does (verified: CREATE fails with
  "access denied" for a normal account).
* A Scheduled Task, offered only as an explicit opt-in for a machine where an
  administrator wants the service up before anyone signs in.

The launcher is ``pythonw.exe`` so nothing pops up a console window at sign-in.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from .deploy_core import resolve_project_root
except ImportError:  # Executed directly by the Windows launcher.
    from deploy_core import resolve_project_root

SHORTCUT_NAME = 'EasyOJ Server.lnk'
TASK_NAME = 'EasyOJ Server'
LAUNCHER_RELATIVE = Path('scripts') / 'start_service.py'


@dataclass(frozen=True)
class AutostartStatus:
    installed: bool
    method: str = ''
    location: str = ''
    detail: str = ''


def startup_folder() -> Path:
    """Per-user Startup folder. Writable without elevation."""
    appdata = os.environ.get('APPDATA')
    if not appdata:
        raise RuntimeError('APPDATA is not set; cannot locate the Startup folder')
    return Path(appdata) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'


def _shortcut_path() -> Path:
    return startup_folder() / SHORTCUT_NAME


def launcher_command(root: Path) -> tuple[Path, Path]:
    """Return (interpreter, script) for a windowless service start."""
    root = resolve_project_root(root)
    # pythonw.exe runs without allocating a console, so sign-in stays quiet.
    interpreter = root / '.venv' / 'Scripts' / 'pythonw.exe'
    if not interpreter.is_file():
        interpreter = root / '.venv' / 'Scripts' / 'python.exe'
    script = root / LAUNCHER_RELATIVE
    if not interpreter.is_file():
        raise RuntimeError('Project Python is missing. Run Initialize / repair first.')
    if not script.is_file():
        raise RuntimeError(f'Missing service launcher: {script}')
    return interpreter, script


def status(root: Path) -> AutostartStatus:
    """Report whichever mechanism is currently in place."""
    try:
        shortcut = _shortcut_path()
    except RuntimeError as exc:
        return AutostartStatus(False, detail=str(exc))
    if shortcut.is_file():
        return AutostartStatus(True, 'startup-folder', str(shortcut))
    if _task_exists():
        return AutostartStatus(True, 'scheduled-task', TASK_NAME)
    return AutostartStatus(False)


def install_shortcut(root: Path) -> AutostartStatus:
    """Create the Startup-folder shortcut. No elevation required."""
    root = resolve_project_root(root)
    interpreter, script = launcher_command(root)
    target = _shortcut_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        import win32com.client
    except ImportError as exc:  # pragma: no cover - pywin32 is a project dependency
        raise RuntimeError('pywin32 is required to create the startup shortcut') from exc

    shell = win32com.client.Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(str(target))
    shortcut.TargetPath = str(interpreter)
    shortcut.Arguments = f'"{script}"'
    shortcut.WorkingDirectory = str(root)
    shortcut.Description = 'Start the EasyOJ judge and web service'
    shortcut.save()
    return AutostartStatus(True, 'startup-folder', str(target))


def remove_shortcut() -> bool:
    try:
        target = _shortcut_path()
    except RuntimeError:
        return False
    if target.is_file():
        target.unlink()
        return True
    return False


def _run_schtasks(arguments: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['schtasks.exe', *arguments],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        shell=False,
        timeout=30,
    )


def _task_exists() -> bool:
    if os.name != 'nt':
        return False
    try:
        return _run_schtasks(['/query', '/tn', TASK_NAME]).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def install_task(root: Path) -> AutostartStatus:
    """Register a Scheduled Task so the service starts before anyone signs in.

    Requires an elevated process; the caller should present the failure as
    "run as administrator, or use the Startup folder instead".
    """
    root = resolve_project_root(root)
    interpreter, script = launcher_command(root)
    command = f'"{interpreter}" "{script}"'
    result = _run_schtasks(
        ['/create', '/tn', TASK_NAME, '/tr', command, '/sc', 'onstart', '/rl', 'highest', '/f']
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or '').strip()
        raise RuntimeError(f'Could not register the scheduled task: {message}')
    return AutostartStatus(True, 'scheduled-task', TASK_NAME)


def remove_task() -> bool:
    if not _task_exists():
        return False
    return _run_schtasks(['/delete', '/tn', TASK_NAME, '/f']).returncode == 0


def disable(root: Path | None = None) -> list[str]:
    """Remove every autostart entry, reporting what was removed."""
    removed = []
    if remove_shortcut():
        removed.append('startup-folder')
    if remove_task():
        removed.append('scheduled-task')
    return removed


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description='Manage EasyOJ automatic startup')
    parser.add_argument('action', choices=('status', 'enable', 'disable'))
    parser.add_argument('--project-root', default=None)
    parser.add_argument(
        '--method',
        choices=('startup-folder', 'scheduled-task'),
        default='startup-folder',
        help='scheduled-task starts before sign-in but needs administrator rights',
    )
    args = parser.parse_args(argv)
    root = resolve_project_root(args.project_root)

    if args.action == 'status':
        current = status(root)
        if current.installed:
            print(f'Automatic startup is enabled via {current.method}: {current.location}')
        else:
            print('Automatic startup is not enabled.')
            if current.detail:
                print(current.detail, file=sys.stderr)
        return 0

    if args.action == 'disable':
        removed = disable(root)
        print(f'Removed: {", ".join(removed)}' if removed else 'Nothing to remove.')
        return 0

    try:
        result = install_task(root) if args.method == 'scheduled-task' else install_shortcut(root)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f'Automatic startup enabled via {result.method}: {result.location}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
