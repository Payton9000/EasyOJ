from pathlib import Path

from app.judge.sandbox import _resolve_allow_paths
from app.judge.sandbox import build_sandbox_environment


def test_sandbox_environment_does_not_expose_application_secrets(tmp_path):
    work_dir = str(tmp_path / 'work')
    env = build_sandbox_environment(
        work_dir,
        {'g++': str(tmp_path / 'toolchain' / 'mingw64' / 'bin' / 'g++.exe')},
        'cpp',
        base_environment={
            'SECRET_KEY': 'do-not-leak',
            'SystemRoot': r'C:\Windows',
            'LOCALAPPDATA': r'C:\Users\student\AppData\Local',
            'PATH': r'C:\Windows\System32',
        },
    )

    assert 'SECRET_KEY' not in env
    assert env['TEMP'] == work_dir
    assert env['TMP'] == work_dir
    assert env['LOCALAPPDATA'].endswith(r'work\localappdata')
    assert 'mingw64' in env['PATH'].lower()


def test_cpp_allow_paths_include_local_toolchain(tmp_path):
    gpp = tmp_path / 'toolchain' / 'mingw64' / 'bin' / 'g++.exe'
    paths = _resolve_allow_paths([], str(tmp_path / 'work'), {'g++': str(gpp)}, 'cpp')

    assert Path(gpp).parent in {Path(path) for path in paths}


def test_language_environment_does_not_expose_other_compilers(tmp_path):
    paths = {
        'g++': str(tmp_path / 'toolchain' / 'mingw64' / 'bin' / 'g++.exe'),
        'javac': str(tmp_path / 'toolchain' / 'jdk' / 'bin' / 'javac.exe'),
        'java': str(tmp_path / 'toolchain' / 'jdk' / 'bin' / 'java.exe'),
        'python': str(tmp_path / '.venv' / 'Scripts' / 'python.exe'),
    }

    env = build_sandbox_environment(str(tmp_path / 'work'), paths, 'python')

    assert 'mingw64' not in env['PATH'].lower()
    assert r'jdk\bin' not in env['PATH'].lower()
    assert '.venv' in env['PATH'].lower()


def test_python_allow_paths_include_venv_metadata_parent(tmp_path):
    python_exe = tmp_path / '.venv' / 'Scripts' / 'python.exe'
    paths = _resolve_allow_paths(
        [],
        str(tmp_path / 'work'),
        {'python': str(python_exe)},
        'python',
    )

    assert python_exe.parent in {Path(path) for path in paths}
    assert python_exe.parent.parent in {Path(path) for path in paths}
