"""First-run setup values: validate and persist port/site name into .env.

The operator-facing form lives in setup_server.py (loopback webpage). This
module must not import Flask or app/__init__.py: system Python on the first
double-click has neither.
"""

from __future__ import annotations

import importlib.util
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_validation():
    """Load validators without importing app/__init__.py (that module needs Flask)."""
    path = PROJECT_ROOT / 'app' / 'utils' / 'validation.py'
    spec = importlib.util.spec_from_file_location('_easyoj_setup_validation', path)
    if spec is None or spec.loader is None:
        raise ImportError(f'Cannot load validators from {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_validation = _load_validation()
validate_email = _validation.validate_email
validate_password = _validation.validate_password
validate_username = _validation.validate_username

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
    """The operator closed the setup page without finishing."""


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
    os.environ['EASYOJ_PORT'] = str(choices.port)
    os.environ['EASYOJ_SITE_NAME'] = choices.site_name
