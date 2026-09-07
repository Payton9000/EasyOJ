"""One-double-click launcher: set up if needed, start the service, open a browser.

The teacher who runs this should not have to know what a virtual environment or a
SECRET_KEY is. Everything the service needs is created on first run; later runs go
straight to serving.

Called by ``启动 EasyOJ.bat`` at the project root. Kept in Python rather than
batch because the setup steps need real error handling, and the same logic then
works for the tray GUI and the auto-start launcher.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

VENV_PYTHON = PROJECT_ROOT / '.venv' / 'Scripts' / 'python.exe'
VENV_PYTHONW = PROJECT_ROOT / '.venv' / 'Scripts' / 'pythonw.exe'
SERVICE_SCRIPT = PROJECT_ROOT / 'scripts' / 'start_service.py'
BOOTSTRAP = PROJECT_ROOT / 'scripts' / 'deploy' / 'windows' / 'bootstrap.ps1'


def say(message: str = '') -> None:
    print(message, flush=True)


def _port_in_use(port: int) -> bool:
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return True
    except OSError:
        return False


def _configured_port() -> int:
    env_file = PROJECT_ROOT / '.env'
    raw = os.environ.get('EASYOJ_PORT', '')
    if not raw and env_file.is_file():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            if line.strip().startswith('EASYOJ_PORT='):
                raw = line.split('=', 1)[1].strip()
                break
    try:
        return max(1, min(65535, int(raw or 5000)))
    except ValueError:
        return 5000


def _system_python() -> list[str] | None:
    """Find an interpreter able to create the project virtual environment."""
    for candidate in (['py', '-3'], ['python'], ['python3']):
        try:
            result = subprocess.run(
                [*candidate, '--version'],
                capture_output=True,
                text=True,
                timeout=15,
                shell=False,
            )
            if result.returncode == 0:
                return candidate
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def _run(command: list[str], *, timeout: int = 3600, env: dict[str, str] | None = None) -> int:
    say('> ' + subprocess.list2cmdline(command))
    try:
        return subprocess.run(
            command, cwd=str(PROJECT_ROOT), shell=False, timeout=timeout, env=env
        ).returncode
    except subprocess.TimeoutExpired:
        say(f'This step took longer than {timeout}s and was stopped.')
        return 1
    except OSError as exc:
        say(f'Could not run the command: {exc}')
        return 1


def ensure_environment() -> bool:
    """Create .venv, install dependencies, and prepare data/.env on first run."""
    if VENV_PYTHON.is_file():
        return True

    say('First run: preparing EasyOJ. This downloads the compilers and may take')
    say('a while on a slow connection. You only need to do this once.')
    say()
    if not BOOTSTRAP.is_file():
        say(f'Setup script is missing: {BOOTSTRAP}')
        return False
    python = _system_python()
    if python is None:
        say('Python 3.10 or newer is required and was not found.')
        say('Install it from https://www.python.org/downloads/ and tick')
        say('"Add python.exe to PATH", then run this file again.')
        return False

    code = _run(
        [
            'powershell.exe',
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            str(BOOTSTRAP),
            '-ProjectRoot',
            str(PROJECT_ROOT),
        ]
    )
    if code != 0 or not VENV_PYTHON.is_file():
        say()
        say('Setup did not finish. Scroll up for the first error message.')
        return False
    return True


def ensure_configuration() -> bool:
    """Create data directories, .env (with a generated SECRET_KEY), and the database.

    A brand-new installation runs the setup wizard first so the operator chooses
    the administrator account and port. Without it the password was generated,
    printed among thirty lines of problem-import output, and lost when the window
    closed - leaving no way to sign in.
    """
    sys.path.insert(0, str(PROJECT_ROOT / 'scripts' / 'deploy' / 'windows'))
    try:
        from deploy_core import ensure_project_layout
        from deploy_core import generate_env_file
    except ImportError as exc:
        say(f'Could not load the deployment helpers: {exc}')
        return False

    ensure_project_layout(PROJECT_ROOT)
    first_run = not (PROJECT_ROOT / 'data' / 'database.db').is_file()
    environment = dict(os.environ)

    if not first_run:
        generate_env_file(PROJECT_ROOT)
        return True

    sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))
    try:
        from setup_wizard import SetupCancelled
        from setup_wizard import apply_choices
        from setup_wizard import run_wizard
    except ImportError as exc:
        say(f'Could not load the setup wizard: {exc}')
        return False

    try:
        choices = run_wizard()
    except SetupCancelled:
        say('Setup was cancelled. Nothing has been changed.')
        return False

    apply_choices(choices)
    # Credentials travel through the environment; argv is visible to other
    # processes on the machine.
    environment['EASYOJ_INITIAL_ADMIN_USERNAME'] = choices.admin_username
    environment['EASYOJ_INITIAL_ADMIN_EMAIL'] = choices.admin_email
    environment['EASYOJ_INITIAL_ADMIN_PASSWORD'] = choices.admin_password
    # Typed and confirmed in the wizard just now, so no forced change is needed.
    environment['EASYOJ_INITIAL_ADMIN_PASSWORD_CONFIRMED'] = '1'
    say()
    say(f'Setting up "{choices.site_name}" on port {choices.port}...')
    say('Creating the database and importing the built-in problems...')
    code = _run(
        [str(VENV_PYTHON), str(PROJECT_ROOT / 'init_db.py')],
        timeout=900,
        env=environment,
    )
    if code != 0:
        say('Database initialization failed.')
        return False
    say()
    say(f'Setup finished. Sign in as "{choices.admin_username}" with the password you chose.')
    return True


def start_service(port: int, *, open_browser: bool = True) -> bool:
    """Start the service detached so closing this window leaves it running."""
    interpreter = VENV_PYTHONW if VENV_PYTHONW.is_file() else VENV_PYTHON
    flags = 0
    if os.name == 'nt':
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    subprocess.Popen(
        [str(interpreter), str(SERVICE_SCRIPT)],
        cwd=str(PROJECT_ROOT),
        creationflags=flags,
        close_fds=True,
    )

    say('Starting EasyOJ...')
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if _port_in_use(port):
            break
        time.sleep(0.5)
    else:
        say()
        say('EasyOJ did not answer within 90 seconds.')
        say(f'See {PROJECT_ROOT / "data" / "logs" / "service.log"} for the reason.')
        return False

    url = f'http://localhost:{port}'
    say()
    say('=' * 58)
    say('  EasyOJ is running.')
    say(f'  On this computer:      {url}')
    for address in _lan_addresses():
        say(f'  From the classroom:    http://{address}:{port}')
    say('=' * 58)
    say()
    say('The service keeps running after this window closes.')
    say('To stop it, run "停止 EasyOJ.bat".')
    if open_browser:
        webbrowser.open(url)
    return True


def _lan_addresses() -> list[str]:
    """Best-effort LAN addresses so the teacher can tell students where to go."""
    found = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No packet is sent; this just selects the default outbound interface.
            probe.connect(('10.255.255.255', 1))
            found.append(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    return [address for address in found if not address.startswith('127.')]


def stop_service(port: int) -> bool:
    """Stop whatever is serving on the configured port."""
    if not _port_in_use(port):
        say('EasyOJ is not running.')
        return True
    stopped = False
    try:
        import psutil
    except ImportError:
        psutil = None

    if psutil is not None:
        for connection in psutil.net_connections(kind='inet'):
            if connection.laddr and connection.laddr.port == port and connection.pid:
                try:
                    process = psutil.Process(connection.pid)
                    say(f'Stopping process {connection.pid} ({process.name()})...')
                    process.terminate()
                    process.wait(timeout=15)
                    stopped = True
                except Exception:
                    try:
                        psutil.Process(connection.pid).kill()
                        stopped = True
                    except Exception:
                        pass
                break

    if not _port_in_use(port):
        say('EasyOJ stopped.')
        return True
    say('Could not stop EasyOJ automatically. Restarting the computer will clear it.')
    return stopped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Start or stop EasyOJ')
    parser.add_argument('action', nargs='?', default='start', choices=('start', 'stop'))
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)

    port = _configured_port()

    if args.action == 'stop':
        return 0 if stop_service(port) else 1

    if _port_in_use(port):
        url = f'http://localhost:{port}'
        say(f'EasyOJ is already running at {url}')
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    if not ensure_environment():
        return 1
    if not ensure_configuration():
        return 1
    return 0 if start_service(port, open_browser=not args.no_browser) else 1


if __name__ == '__main__':
    raise SystemExit(main())
