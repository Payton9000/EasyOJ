"""Small Tkinter deployment assistant for a single Windows LAN host."""

from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from collections.abc import Iterable
from pathlib import Path

try:
    from . import autostart
    from .deploy_core import ensure_project_layout
    from .deploy_core import generate_env_file
    from .deploy_core import resolve_project_root
    from .tray_icon import TrayIcon
except ImportError:  # Executed directly by the Windows launcher.
    import autostart
    from deploy_core import ensure_project_layout
    from deploy_core import generate_env_file
    from deploy_core import resolve_project_root
    from tray_icon import TrayIcon


class DeploymentError(RuntimeError):
    pass


HEALTH_MARKER = {'service': 'easyoj', 'status': 'ok', 'version': 1}
PRODUCTION_LOG_RELATIVE_PATH = Path('data') / 'logs' / 'production.log'
PRODUCTION_LOG_MAX_BYTES = 2 * 1024 * 1024
PRODUCTION_LOG_BACKUPS = 3


class BoundedDeploymentLog:
    """Append deployment output while keeping a small, recoverable log history."""

    def __init__(
        self,
        path: Path,
        *,
        max_bytes: int = PRODUCTION_LOG_MAX_BYTES,
        backups: int = PRODUCTION_LOG_BACKUPS,
    ) -> None:
        self.path = path
        self.max_bytes = max(1024, max_bytes)
        self.backups = max(1, backups)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, message: str) -> None:
        data = (message.rstrip('\r\n') + '\n').encode('utf-8', errors='replace')
        with self._lock:
            if self.path.is_file() and self.path.stat().st_size + len(data) > self.max_bytes:
                self._rotate()
            if len(data) > self.max_bytes:
                data = data[-self.max_bytes :]
            with self.path.open('ab') as stream:
                stream.write(data)

    def _rotate(self) -> None:
        oldest = self.path.with_name(f'{self.path.name}.{self.backups}')
        if oldest.exists():
            oldest.unlink()
        for index in range(self.backups - 1, 0, -1):
            source = self.path.with_name(f'{self.path.name}.{index}')
            if source.exists():
                source.replace(self.path.with_name(f'{self.path.name}.{index + 1}'))
        if self.path.exists():
            self.path.replace(self.path.with_name(f'{self.path.name}.1'))


def _read_log_tail(path: Path, max_bytes: int = 16 * 1024) -> str:
    if not path.is_file():
        return '(no production output was captured)'
    with path.open('rb') as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - max_bytes))
        return stream.read().decode('utf-8', errors='replace').strip() or '(empty)'


def _capture_process_output(
    process: subprocess.Popen, deployment_log: BoundedDeploymentLog
) -> None:
    output = getattr(process, 'stdout', None)
    if output is None:
        return
    try:
        lines: Iterable[bytes | str] = output
        for line in lines:
            if isinstance(line, bytes):
                line = line.decode('utf-8', errors='replace')
            deployment_log.append(line)
    finally:
        close = getattr(output, 'close', None)
        if close is not None:
            close()


def _stop_failed_process(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except (subprocess.TimeoutExpired, OSError):
            process.kill()


def _configured_port(root: Path) -> int:
    values = {}
    env_file = root / '.env'
    if env_file.is_file():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip()
    raw_port = os.environ.get('EASYOJ_PORT') or values.get('EASYOJ_PORT') or '5000'
    try:
        return max(1, min(65535, int(raw_port)))
    except ValueError:
        return 5000


def _port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.2):
            return True
    except OSError:
        return False


def _wait_for_server(port: int, timeout_seconds: float = 10) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f'http://127.0.0.1:{port}/healthz', timeout=0.5
            ) as response:
                if response.status == 200:
                    payload = response.read().decode('utf-8')
                    if json.loads(payload) == HEALTH_MARKER:
                        return True
        except (OSError, ValueError, TypeError, urllib.error.URLError):
            pass
        time.sleep(0.2)
    return False


def _powershell_executable() -> str:
    return 'powershell.exe'


def run_step(
    command: list[str],
    *,
    cwd: Path,
    log: Callable[[str], None],
    timeout_seconds: int = 3600,
) -> None:
    """Run one bounded deployment command without invoking a shell."""
    log('> ' + subprocess.list2cmdline(command))
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        shell=False,
    )
    try:
        output, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.communicate()
        raise DeploymentError(f'Deployment step timed out after {timeout_seconds}s') from exc
    if output:
        for line in output.splitlines():
            log(line)
    if process.returncode != 0:
        raise DeploymentError(f'Deployment step failed with exit code {process.returncode}')


def run_install(root: Path, log: Callable[[str], None]) -> None:
    """Run the project-local bootstrap and initialize the database."""
    root = resolve_project_root(root)
    ensure_project_layout(root)
    generate_env_file(root)
    bootstrap = root / 'scripts' / 'deploy' / 'windows' / 'bootstrap.ps1'
    if not bootstrap.is_file():
        raise DeploymentError(f'Missing bootstrap script: {bootstrap}')
    run_step(
        [
            _powershell_executable(),
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            str(bootstrap),
            '-ProjectRoot',
            str(root),
        ],
        cwd=root,
        log=log,
        timeout_seconds=10800,
    )
    python_path = root / '.venv' / 'Scripts' / 'python.exe'
    if not python_path.is_file():
        raise DeploymentError('Project Python is missing after Initialize.')
    log('Initializing the local database...')
    run_step(
        [str(python_path), str(root / 'init_db.py')],
        cwd=root,
        log=log,
        timeout_seconds=900,
    )


def run_server(root: Path, log: Callable[[str], None]) -> None:
    root = resolve_project_root(root)
    python_path = root / '.venv' / 'Scripts' / 'python.exe'
    if not python_path.is_file():
        raise DeploymentError('Project Python is missing. Run Initialize first.')
    port = _configured_port(root)
    if _port_is_open(port):
        raise DeploymentError(f'Port {port} is already in use; the server may already be running.')
    flags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    if os.name == 'nt':
        flags |= getattr(subprocess, 'DETACHED_PROCESS', 0)
        flags |= getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    production_log = BoundedDeploymentLog(root / PRODUCTION_LOG_RELATIVE_PATH)
    production_log.append('Starting EasyOJ production server')
    process = subprocess.Popen(
        [str(python_path), 'run.py', 'production'],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        creationflags=flags,
        shell=False,
    )
    capture_thread = threading.Thread(
        target=_capture_process_output,
        args=(process, production_log),
        name='EasyOJProductionLog',
        daemon=True,
    )
    capture_thread.start()
    if not _wait_for_server(port):
        _stop_failed_process(process)
        capture_thread.join(timeout=1)
        tail = _read_log_tail(root / PRODUCTION_LOG_RELATIVE_PATH)
        raise DeploymentError(
            f'Server did not become ready on port {port}. '
            f'Production log: {root / PRODUCTION_LOG_RELATIVE_PATH}\n{tail}'
        )
    log(
        f'Server started (PID {process.pid}). '
        f'Open http://localhost:{port} or the host LAN address.'
    )


def run_backup(root: Path, log: Callable[[str], None]) -> None:
    """Write a hot database backup without stopping the running service."""
    root = resolve_project_root(root)
    python_path = root / '.venv' / 'Scripts' / 'python.exe'
    if not python_path.is_file():
        raise DeploymentError('Project Python is missing. Run Initialize first.')
    script = root / 'scripts' / 'backup_now.py'
    if not script.is_file():
        raise DeploymentError(f'Missing backup script: {script}')
    run_step(
        [str(python_path), str(script)],
        cwd=root,
        log=log,
        timeout_seconds=600,
    )


def enable_autostart(root: Path, log: Callable[[str], None]) -> None:
    """Start EasyOJ automatically at sign-in, without needing administrator rights."""
    root = resolve_project_root(root)
    try:
        result = autostart.install_shortcut(root)
    except RuntimeError as exc:
        raise DeploymentError(str(exc)) from exc
    log(f'Automatic startup enabled ({result.method}).')
    log(f'Shortcut: {result.location}')
    log('EasyOJ will start in the background the next time you sign in.')


def disable_autostart(root: Path, log: Callable[[str], None]) -> None:
    removed = autostart.disable(resolve_project_root(root))
    if removed:
        log(f'Automatic startup removed ({", ".join(removed)}).')
    else:
        log('Automatic startup was not enabled.')


def create_app(root: Path) -> None:
    import tkinter as tk
    from tkinter import scrolledtext

    root = resolve_project_root(root)
    events: queue.Queue[str] = queue.Queue()
    window = tk.Tk()
    window.title('EasyOJ Windows Deployment')
    window.geometry('760x500')
    window.minsize(620, 380)

    frame = tk.Frame(window, padx=16, pady=16)
    frame.pack(fill='both', expand=True)
    tk.Label(frame, text='EasyOJ deployment', font=('Segoe UI', 15, 'bold')).pack(anchor='w')
    tk.Label(
        frame,
        text=f'Project folder: {root}',
        anchor='w',
        justify='left',
    ).pack(fill='x', pady=(4, 2))
    autostart_label = tk.Label(frame, text='', anchor='w', justify='left', fg='#475467')
    autostart_label.pack(fill='x', pady=(0, 12))

    def refresh_autostart_label() -> None:
        try:
            current = autostart.status(root)
        except Exception:
            autostart_label.configure(text='Automatic startup: unknown')
            return
        if current.installed:
            autostart_label.configure(
                text=f'Automatic startup: ON ({current.method})', fg='#1c7c4a'
            )
        else:
            autostart_label.configure(text='Automatic startup: off', fg='#475467')

    output = scrolledtext.ScrolledText(frame, height=18, state='disabled', font=('Consolas', 9))
    output.pack(fill='both', expand=True)
    buttons = tk.Frame(frame)
    buttons.pack(fill='x', pady=(12, 0))
    busy = {'value': False}

    def append(message: str) -> None:
        output.configure(state='normal')
        output.insert('end', message + '\n')
        output.see('end')
        output.configure(state='disabled')

    def worker(action: Callable[[Path, Callable[[str], None]], None]) -> None:
        try:
            action(root, events.put)
            events.put('Completed successfully.')
        except Exception as exc:  # GUI boundary: show a concise actionable error.
            events.put(f'ERROR: {exc}')
        finally:
            busy['value'] = False

    def start(action: Callable[[Path, Callable[[str], None]], None]) -> None:
        if busy['value']:
            return
        busy['value'] = True
        for button in buttons.winfo_children():
            button.configure(state='disabled')
        threading.Thread(target=worker, args=(action,), daemon=True).start()

    def poll_events() -> None:
        try:
            while True:
                append(events.get_nowait())
        except queue.Empty:
            pass
        if not busy['value']:
            for button in buttons.winfo_children():
                button.configure(state='normal')
        window.after(150, poll_events)

    # The server keeps running in its own detached process, so hiding this window
    # is safe. Minimising to the notification area keeps it out of the taskbar for
    # the rest of the school day without the operator having to stop anything.
    state = {'server_running': False}
    tray = TrayIcon(
        'EasyOJ deployment',
        on_open=lambda: window.after(0, restore_window),
        on_exit=lambda: window.after(0, quit_assistant),
    )

    def tray_tooltip() -> str:
        if state['server_running']:
            return f'EasyOJ - serving on port {_configured_port(root)}'
        return 'EasyOJ deployment assistant'

    def hide_to_tray() -> None:
        if not tray.available:
            window.iconify()
            return
        if not tray.show(tray_tooltip()):
            window.iconify()
            return
        window.withdraw()
        append('Minimised to the notification area. Double-click the icon to reopen.')

    def restore_window() -> None:
        tray.hide()
        window.deiconify()
        window.lift()
        window.focus_force()

    def quit_assistant() -> None:
        tray.stop()
        window.destroy()

    def on_close() -> None:
        # Closing the window must not look like it stopped a running server.
        if state['server_running']:
            hide_to_tray()
            tray.notify('EasyOJ', 'The server is still running in the background.')
        else:
            quit_assistant()

    def start_server_and_track(project_root: Path, log: Callable[[str], None]) -> None:
        run_server(project_root, log)
        state['server_running'] = True
        window.after(0, lambda: tray.update_tooltip(tray_tooltip()))

    def toggle_autostart() -> None:
        """One button: enable when off, remove when on."""
        try:
            currently_on = autostart.status(root).installed
        except Exception:
            currently_on = False
        action = disable_autostart if currently_on else enable_autostart

        def run(project_root: Path, log: Callable[[str], None]) -> None:
            action(project_root, log)
            window.after(0, refresh_autostart_label)
            window.after(0, sync_autostart_button)

        start(run)

    def sync_autostart_button() -> None:
        try:
            currently_on = autostart.status(root).installed
        except Exception:
            currently_on = False
        autostart_button.configure(
            text='Remove auto-start' if currently_on else 'Start with Windows'
        )

    tk.Button(buttons, text='Initialize / repair', command=lambda: start(run_install)).pack(
        side='left'
    )
    tk.Button(buttons, text='Start server', command=lambda: start(start_server_and_track)).pack(
        side='left', padx=(8, 0)
    )
    tk.Button(buttons, text='Back up now', command=lambda: start(run_backup)).pack(
        side='left', padx=(8, 0)
    )
    autostart_button = tk.Button(buttons, text='Start with Windows', command=toggle_autostart)
    autostart_button.pack(side='left', padx=(8, 0))
    tk.Button(buttons, text='Minimise to tray', command=hide_to_tray).pack(side='left', padx=(8, 0))
    tk.Button(buttons, text='Close', command=on_close).pack(side='right')

    window.protocol('WM_DELETE_WINDOW', on_close)
    tray.start()
    refresh_autostart_label()
    sync_autostart_button()
    append('Choose Initialize / repair before the first launch.')
    if not tray.available:
        append('Notification-area icon is unavailable; Minimise will use the taskbar.')
    window.after(150, poll_events)
    try:
        window.mainloop()
    finally:
        tray.stop()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description='EasyOJ Windows deployment GUI')
    parser.add_argument('--project-root', default=None)
    args = parser.parse_args()
    create_app(resolve_project_root(args.project_root))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
