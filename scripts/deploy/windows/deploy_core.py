"""Safe, repeatable deployment primitives for a Windows EasyOJ installation.

The module intentionally performs no network access and never changes the
current machine's global PATH.  The GUI and PowerShell launcher build on these
small functions so they can be tested without installing a toolchain.
"""

from __future__ import annotations

import argparse
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

# Chosen by the first-run wizard; regenerating .env must not reset them.
PRESERVED_ENV_KEYS = ('EASYOJ_PORT', 'EASYOJ_SITE_NAME')

MANAGED_ENV_DEFAULTS = {
    'FLASK_ENV': 'production',
    'EASYOJ_HOST': '0.0.0.0',
    'EASYOJ_PORT': '5000',
    'JUDGE_QUEUE_MAXSIZE': '200',
    'JUDGE_REQUIRE_SANDBOX': '1',
    'SANDBOX_ENABLED': '1',
    'SANDBOX_APP_CONTAINER': '1',
    'SANDBOX_STRICT_APP_CONTAINER': '1',
    'SANDBOX_MAX_PROCESSES': '8',
    'MAX_OUTPUT_SIZE': '65536',
    'SUBMISSION_RATE_MAX': '30',
    'SUBMISSION_RATE_WINDOW_SECONDS': '60',
    'SUBMISSION_RATE_MAX_ENTRIES': '10000',
    'MAX_TIME_LIMIT_MS': '20000',
    'MAX_MEMORY_LIMIT_MB': '512',
    'SANDBOX_MAX_WORKSPACE_BYTES': '67108864',
    'SANDBOX_MAX_WORKSPACE_FILES': '1024',
}


@dataclass(frozen=True)
class DeployPaths:
    root: Path
    data_dir: Path
    judge_log_dir: Path
    submission_dir: Path
    temp_dir: Path
    toolchain_dir: Path
    venv_dir: Path
    env_file: Path

    @classmethod
    def from_root(cls, root: Path, env_path: Path | None = None) -> DeployPaths:
        root = root.resolve()
        return cls(
            root=root,
            data_dir=root / 'data',
            judge_log_dir=root / 'data' / 'judge_logs',
            submission_dir=root / 'data' / 'submissions',
            temp_dir=root / 'data' / 'temp',
            toolchain_dir=root / 'toolchain',
            venv_dir=root / '.venv',
            env_file=(env_path or root / '.env').resolve(),
        )


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def resolve_project_root(value: str | os.PathLike[str] | Path | None = None) -> Path:
    candidate = Path(value) if value else Path(__file__).resolve().parents[3]
    candidate = candidate.resolve()
    if not candidate.is_dir():
        raise ValueError(f'Project root is not a directory: {candidate}')
    if not (candidate / 'run.py').is_file() or not (candidate / 'app').is_dir():
        raise ValueError(f'Not an EasyOJ project root: {candidate}')
    return candidate


def ensure_project_layout(root: str | os.PathLike[str] | Path) -> DeployPaths:
    paths = DeployPaths.from_root(resolve_project_root(root))
    for directory in (
        paths.data_dir,
        paths.judge_log_dir,
        paths.submission_dir,
        paths.temp_dir,
        paths.toolchain_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def _read_env_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        key, value = stripped.split('=', 1)
        if key and key.replace('_', '').isalnum():
            values[key] = value
    return values


def _usable_secret(value: str | None) -> bool:
    normalized = (value or '').strip().lower()
    return len(normalized) >= 32 and normalized not in {
        'change-me-to-a-random-string',
        'change-me',
    }


def generate_env_file(
    root: str | os.PathLike[str] | Path,
    *,
    env_path: str | os.PathLike[str] | Path | None = None,
) -> Path:
    """Create/update managed settings without replacing an existing secret."""
    project_root = resolve_project_root(root)
    target = Path(env_path).resolve() if env_path else project_root / '.env'
    if not _is_within(target, project_root):
        raise ValueError('.env must remain inside the project root')

    old_values = _read_env_values(target)
    values = dict(MANAGED_ENV_DEFAULTS)
    for key in PRESERVED_ENV_KEYS:
        if old_values.get(key):
            values[key] = old_values[key]
    old_secret = old_values.get('SECRET_KEY')
    values['SECRET_KEY'] = (
        old_secret.strip() if _usable_secret(old_secret) else secrets.token_hex(32)
    )

    lines = [
        '# EasyOJ local Windows deployment. Keep this file private.',
        '# Managed values are refreshed by the deployment assistant.',
    ]
    for key, value in values.items():
        lines.append(f'{key}={value}')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    return target


def _first_existing(candidates: list[Path], fallback: Path) -> Path:
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file() and resolved.name.lower() in {
            'g++.exe',
            'javac.exe',
            'java.exe',
            'python.exe',
        }:
            return resolved
    return fallback.resolve()


def _jdk_bin(root: Path) -> Path:
    jdk_root = (root / 'toolchain' / 'jdk').resolve()
    candidates = [jdk_root / 'bin']
    if jdk_root.is_dir():
        candidates.extend(sorted(path / 'bin' for path in jdk_root.iterdir() if path.is_dir()))
    for candidate in candidates:
        if _is_within(candidate, root) and (candidate / 'javac.exe').is_file():
            return candidate
    return jdk_root / 'bin'


def build_local_toolchain_paths(root: str | os.PathLike[str] | Path) -> dict[str, str]:
    """Return absolute compiler/interpreter paths that are all project-owned."""
    project_root = resolve_project_root(root)
    mingw_bin = project_root / 'toolchain' / 'mingw64' / 'bin'
    jdk_bin = _jdk_bin(project_root)
    python_candidates = [
        project_root / 'runtime' / 'python' / 'python.exe',
        project_root / 'toolchain' / 'python' / 'python.exe',
        project_root / '.venv' / 'Scripts' / 'python.exe',
    ]
    return {
        'g++': str(_first_existing([mingw_bin / 'g++.exe'], mingw_bin / 'g++.exe')),
        'javac': str(_first_existing([jdk_bin / 'javac.exe'], jdk_bin / 'javac.exe')),
        'java': str(_first_existing([jdk_bin / 'java.exe'], jdk_bin / 'java.exe')),
        'python': str(_first_existing(python_candidates, python_candidates[-1])),
    }


def local_python(root: str | os.PathLike[str] | Path) -> Path | None:
    project_root = resolve_project_root(root)
    candidates = [
        project_root / 'runtime' / 'python' / 'python.exe',
        project_root / 'toolchain' / 'python' / 'python.exe',
        project_root / '.venv' / 'Scripts' / 'python.exe',
    ]
    return next(
        (
            path.resolve()
            for path in candidates
            if path.is_file() and _is_within(path, project_root)
        ),
        None,
    )


def deployment_status(root: str | os.PathLike[str] | Path) -> dict[str, object]:
    project_root = resolve_project_root(root)
    toolchain = build_local_toolchain_paths(project_root)
    return {
        'root': str(project_root),
        'env_ready': (project_root / '.env').is_file(),
        'python_ready': local_python(project_root) is not None,
        'toolchain': {key: Path(value).is_file() for key, value in toolchain.items()},
        'database_ready': (project_root / 'data' / 'database.db').is_file(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Prepare a local EasyOJ Windows installation')
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--write-env', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)

    root = resolve_project_root(args.project_root)
    if args.write_env:
        ensure_project_layout(root)
        print(f'Created {generate_env_file(root)}')
    if args.check or not args.write_env:
        status = deployment_status(root)
        for key, value in status.items():
            print(f'{key}: {value}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
