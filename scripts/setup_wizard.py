"""First-run setup wizard: collect the few decisions only the operator can make.

Before this existed, first run generated a random administrator password, printed
it among thirty lines of problem-import output, and the launcher window closed
eight seconds later. That password is the only way into the system, so in practice
it was lost and the installation was unusable.

The wizard asks for an administrator account, the port, and the site name, then
hands the values to the initializer. It is a Tkinter dialog when a desktop is
available and falls back to console prompts otherwise, so it also works over a
remote session.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.utils.validation import validate_email  # noqa: E402
from app.utils.validation import validate_password  # noqa: E402
from app.utils.validation import validate_username  # noqa: E402

DEFAULT_PORT = 5000
DEFAULT_SITE_NAME = 'EasyOJ'
DEFAULT_USERNAME = 'admin'
DEFAULT_EMAIL = 'admin@oj.local'


@dataclass
class SetupChoices:
    admin_username: str = DEFAULT_USERNAME
    admin_email: str = DEFAULT_EMAIL
    admin_password: str = ''
    port: int = DEFAULT_PORT
    site_name: str = DEFAULT_SITE_NAME


class SetupCancelled(RuntimeError):
    """The operator closed the wizard without finishing."""


def port_is_free(port: int) -> bool:
    """A port already in use would make the service unreachable after setup.

    Binding to 0.0.0.0 alone is not enough: on Windows a listener bound only to
    127.0.0.1 still leaves 0.0.0.0 bindable, so try to connect as well.
    SO_REUSEADDR is deliberately not set, as it would mask the very conflict this
    is probing for.
    """
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.3):
            return False  # Something is already answering there.
    except OSError:
        pass
    for host in ('0.0.0.0', '127.0.0.1'):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((host, port))
        except OSError:
            return False
    return True


def suggest_port(preferred: int = DEFAULT_PORT) -> int:
    for candidate in (preferred, 5001, 8000, 8080, 8081):
        if port_is_free(candidate):
            return candidate
    return preferred


def validate_choices(choices: SetupChoices, confirm_password: str | None = None) -> list[str]:
    """Return human-readable problems; an empty list means the values are usable."""
    errors: list[str] = []
    try:
        choices.admin_username = validate_username(choices.admin_username)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        choices.admin_email = validate_email(choices.admin_email)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        validate_password(choices.admin_password)
    except ValueError as exc:
        errors.append(str(exc))
    if confirm_password is not None and choices.admin_password != confirm_password:
        errors.append('The two passwords do not match.')

    try:
        port = int(choices.port)
    except (TypeError, ValueError):
        errors.append('Port must be a whole number.')
    else:
        if not 1024 <= port <= 65535:
            errors.append('Port must be between 1024 and 65535.')
        elif not port_is_free(port):
            errors.append(f'Port {port} is already used by another program. Pick another.')
        else:
            choices.port = port

    if not (choices.site_name or '').strip():
        errors.append('Site name cannot be empty.')
    else:
        choices.site_name = choices.site_name.strip()[:60]
    return errors


# --- console front end ------------------------------------------------------


def _ask(prompt: str, default: str = '') -> str:
    suffix = f' [{default}]' if default else ''
    try:
        answer = input(f'{prompt}{suffix}: ').strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise SetupCancelled('Setup was cancelled.') from exc
    return answer or default


def run_console(choices: SetupChoices) -> SetupChoices:
    print()
    print('=' * 60)
    print('  EasyOJ first-time setup')
    print('=' * 60)
    print()
    print('  Answer a few questions and EasyOJ will be ready to use.')
    print('  Press Enter to accept the value in brackets.')
    print()

    while True:
        collected = SetupChoices(
            admin_username=_ask('Administrator username', choices.admin_username),
            admin_email=_ask('Administrator email', choices.admin_email),
            site_name=_ask('Site name shown to students', choices.site_name),
            port=_ask('Port', str(choices.port)),
        )
        password = _ask('Administrator password (at least 8 characters)')
        confirm = _ask('Type the password again')
        collected.admin_password = password

        errors = validate_choices(collected, confirm_password=confirm)
        if not errors:
            return collected
        print()
        for message in errors:
            print(f'  ! {message}')
        print()


# --- Tkinter front end ------------------------------------------------------


def run_dialog(choices: SetupChoices) -> SetupChoices:
    import tkinter as tk
    from tkinter import messagebox

    window = tk.Tk()
    window.title('EasyOJ - First-time setup')
    window.geometry('560x520')
    window.minsize(520, 480)
    window.resizable(False, False)

    result: dict[str, SetupChoices] = {}

    frame = tk.Frame(window, padx=24, pady=20)
    frame.pack(fill='both', expand=True)
    tk.Label(frame, text='Welcome to EasyOJ', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
    tk.Label(
        frame,
        text=(
            'These settings are only needed once.\n'
            'Keep the administrator password somewhere safe: it is how you sign in.'
        ),
        justify='left',
        fg='#475467',
    ).pack(anchor='w', pady=(4, 16))

    fields = tk.Frame(frame)
    fields.pack(fill='x')
    entries: dict[str, tk.Entry] = {}

    def add_row(row: int, label: str, key: str, default: str, *, secret: bool = False) -> None:
        tk.Label(fields, text=label, anchor='w').grid(row=row, column=0, sticky='w', pady=6)
        entry = tk.Entry(fields, width=34, show='*' if secret else '')
        entry.insert(0, default)
        entry.grid(row=row, column=1, sticky='we', padx=(12, 0), pady=6)
        entries[key] = entry

    fields.columnconfigure(1, weight=1)
    add_row(0, 'Administrator username', 'admin_username', choices.admin_username)
    add_row(1, 'Administrator email', 'admin_email', choices.admin_email)
    add_row(2, 'Password (8+ characters)', 'admin_password', '', secret=True)
    add_row(3, 'Repeat password', 'confirm_password', '', secret=True)
    add_row(4, 'Site name', 'site_name', choices.site_name)
    add_row(5, 'Port', 'port', str(choices.port))

    hint = tk.Label(
        frame,
        text=(
            'Students will open http://<this computer>:PORT from the classroom.\n'
            'Leave the port unchanged unless another program already uses it.'
        ),
        justify='left',
        fg='#667085',
        font=('Segoe UI', 8),
    )
    hint.pack(anchor='w', pady=(12, 0))

    error_label = tk.Label(frame, text='', fg='#b42318', justify='left', wraplength=500)
    error_label.pack(anchor='w', pady=(12, 0))

    def submit() -> None:
        collected = SetupChoices(
            admin_username=entries['admin_username'].get(),
            admin_email=entries['admin_email'].get(),
            admin_password=entries['admin_password'].get(),
            site_name=entries['site_name'].get(),
            port=entries['port'].get(),
        )
        errors = validate_choices(collected, confirm_password=entries['confirm_password'].get())
        if errors:
            error_label.configure(text='\n'.join(f'- {message}' for message in errors))
            return
        result['choices'] = collected
        window.destroy()

    def cancel() -> None:
        if messagebox.askokcancel('Cancel setup', 'EasyOJ will not be set up. Close the wizard?'):
            window.destroy()

    buttons = tk.Frame(frame)
    buttons.pack(fill='x', pady=(18, 0))
    tk.Button(buttons, text='Finish setup', command=submit, width=16).pack(side='left')
    tk.Button(buttons, text='Cancel', command=cancel, width=10).pack(side='right')

    window.protocol('WM_DELETE_WINDOW', cancel)
    entries['admin_password'].focus_set()
    window.bind('<Return>', lambda _event: submit())
    window.mainloop()

    if 'choices' not in result:
        raise SetupCancelled('Setup was cancelled.')
    return result['choices']


def _can_use_dialog() -> bool:
    """Tk only helps when a person can see and answer the window.

    A piped or SSH session with no TTY would otherwise open a dialog nobody can
    complete, then sit there until the launcher times out.
    """
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        return False


def run_wizard(*, prefer_dialog: bool = True) -> SetupChoices:
    defaults = SetupChoices(port=suggest_port())
    if prefer_dialog and _can_use_dialog():
        try:
            return run_dialog(defaults)
        except SetupCancelled:
            raise
        except Exception:
            # No desktop (remote session, no Tk): fall back to prompts.
            pass
    return run_console(defaults)


def apply_choices(choices: SetupChoices) -> None:
    """Persist the port and site name into .env before initialization."""
    sys.path.insert(0, str(PROJECT_ROOT / 'scripts' / 'deploy' / 'windows'))
    from deploy_core import ensure_project_layout
    from deploy_core import generate_env_file

    ensure_project_layout(PROJECT_ROOT)
    env_path = generate_env_file(PROJECT_ROOT)

    lines = env_path.read_text(encoding='utf-8').splitlines()
    updated: list[str] = []
    seen = set()
    replacements = {
        'EASYOJ_PORT': str(choices.port),
        'EASYOJ_SITE_NAME': choices.site_name,
    }
    for line in lines:
        key = line.split('=', 1)[0].strip() if '=' in line else ''
        if key in replacements:
            updated.append(f'{key}={replacements[key]}')
            seen.add(key)
        else:
            updated.append(line)
    for key, value in replacements.items():
        if key not in seen:
            updated.append(f'{key}={value}')
    env_path.write_text('\n'.join(updated) + '\n', encoding='utf-8', newline='\n')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='EasyOJ first-time setup')
    parser.add_argument('--console', action='store_true', help='use text prompts')
    parser.add_argument('--emit-json', action='store_true', help='print the collected values')
    args = parser.parse_args(argv)

    try:
        choices = run_wizard(prefer_dialog=not args.console)
    except SetupCancelled as exc:
        print(str(exc), file=sys.stderr)
        return 2

    apply_choices(choices)
    if args.emit_json:
        payload = asdict(choices)
        # The password travels to the initializer through the environment, never
        # through argv (which is visible to other processes) or stdout.
        payload.pop('admin_password', None)
        print(json.dumps(payload))
    os.environ['EASYOJ_INITIAL_ADMIN_PASSWORD'] = choices.admin_password
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
