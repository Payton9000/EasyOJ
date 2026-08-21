"""Run bounded production checks for the Windows LAN deployment."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _project_python():
    local = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if local.is_file():
        return local
    return Path(sys.executable).resolve()


def _run(label, command, timeout):
    print(f'[{label}] ' + subprocess.list2cmdline([str(item) for item in command]))
    try:
        result = subprocess.run(
            [str(item) for item in command],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        print(f'[{label}] timed out after {timeout}s')
        return False
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())
    print(f'[{label}] exit={result.returncode}')
    return result.returncode == 0


def _check_toolchain():
    from scripts.deploy.windows.deploy_core import deployment_status

    status = deployment_status(ROOT)
    print(f'[toolchain] {status}')
    required = ('g++', 'javac', 'java', 'python')
    return all(status['toolchain'].get(key) for key in required) and bool(status['python_ready'])


def _check_sandbox():
    from app.config import Config
    from app.judge.languages import build_compile_command
    from app.judge.languages import build_run_command
    from app.judge.sandbox import SandboxRunner
    from app.judge.sandbox import is_supported
    from scripts.deploy.windows.deploy_core import build_local_toolchain_paths

    supported = is_supported()
    print(f'[sandbox] windows={os.name == "nt"} supported={supported}')
    if os.name != 'nt' or not supported:
        return os.name != 'nt'

    paths = build_local_toolchain_paths(ROOT)
    if not all(Path(paths[key]).is_file() for key in ('g++', 'javac', 'java', 'python')):
        print('[sandbox] local toolchain/runtime is incomplete')
        return False

    data_temp = ROOT / 'data' / 'temp'
    data_temp.mkdir(parents=True, exist_ok=True)
    config = {
        key: getattr(Config, key)
        for key in (
            'JUDGE_REQUIRE_SANDBOX',
            'SANDBOX_APP_CONTAINER',
            'SANDBOX_STRICT_APP_CONTAINER',
            'SANDBOX_PROFILE_NAME',
            'MAX_OUTPUT_SIZE',
            'SANDBOX_MAX_PROCESSES',
            'SANDBOX_MAX_WORKSPACE_BYTES',
            'SANDBOX_MAX_WORKSPACE_FILES',
            'SUPPORTED_LANGUAGES',
        )
    }
    config.update(
        {
            'BASE_DIR': str(ROOT),
            'COMPILER_PATHS': paths,
            'SANDBOX_PROFILE_NAME': 'EasyOJ.Sandbox.Verify',
        }
    )
    runner = SandboxRunner(config)

    def run_checked(label, command, work_dir, language, memory_mb=256):
        result = runner.run(command, str(work_dir), '', 15000, memory_mb, paths, language)
        print(
            f'[sandbox:{label}] status={result.get("status")} '
            f'error={result.get("error", "")[:160]!r} '
            f'workspace={result.get("workspace_bytes", 0)}B/'
            f'{result.get("workspace_files", 0)} files '
            f'output={result.get("output", "")[:80]!r}'
        )
        return result.get('status') == 'OK'

    try:
        with tempfile.TemporaryDirectory(prefix='easyoj-verify-', dir=str(data_temp)) as temp:
            work_dir = Path(temp)

            (work_dir / 'main.py').write_text('print(42)\n', encoding='utf-8')
            python_command = build_run_command(config, str(work_dir), 'python', paths, 128)
            if not run_checked('python', python_command, work_dir, 'python', 128):
                return False

            (work_dir / 'main.cpp').write_text(
                '#include <iostream>\nint main(){std::cout << 42;}\n', encoding='utf-8'
            )
            cpp_compile, _ = build_compile_command(
                config, str(work_dir / 'main.cpp'), 'cpp', str(work_dir), paths
            )
            if not run_checked('cpp-compile', cpp_compile, work_dir, 'cpp', 512):
                return False
            cpp_run = build_run_command(config, str(work_dir), 'cpp', paths, 128)
            if not run_checked('cpp-run', cpp_run, work_dir, 'cpp', 128):
                return False

            (work_dir / 'Main.java').write_text(
                'public class Main { public static void main(String[] a) { '
                'System.out.println(42); } }\n',
                encoding='utf-8',
            )
            java_compile, _ = build_compile_command(
                config, str(work_dir / 'Main.java'), 'java', str(work_dir), paths
            )
            if not run_checked('java-compile', java_compile, work_dir, 'java', 512):
                return False
            java_run = build_run_command(config, str(work_dir), 'java', paths, 256)
            if not run_checked('java-run', java_run, work_dir, 'java', 256):
                return False
    except Exception as exc:
        print(f'[sandbox] smoke test failed: {exc}')
        return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description='Bounded EasyOJ verification')
    parser.add_argument('--safe', action='store_true', required=True, help='required safety gate')
    args = parser.parse_args(argv)
    del args

    python = _project_python()
    checks = [
        (
            'compileall',
            _run('compileall', [python, '-m', 'compileall', '-q', 'app', 'scripts', 'tests'], 120),
        ),
        (
            'ruff-check',
            _run('ruff-check', [python, '-m', 'ruff', 'check', 'app', 'scripts', 'tests'], 120),
        ),
        (
            'ruff-format',
            _run(
                'ruff-format',
                [python, '-m', 'ruff', 'format', '--check', 'app', 'scripts', 'tests'],
                120,
            ),
        ),
        ('pytest', _run('pytest', [python, '-m', 'pytest', '-q', '--maxfail=1'], 300)),
        ('toolchain', _check_toolchain()),
        ('sandbox', _check_sandbox()),
    ]
    failed = [name for name, passed in checks if not passed]
    if failed:
        print('FAILED: ' + ', '.join(failed))
        return 1
    print('All bounded Windows checks passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
