from pathlib import Path

import pytest

from app.judge.compiler import Compiler


def test_cpp_compile_command_uses_absolute_toolchain_and_no_shell(tmp_path):
    compiler = Compiler()
    source = str(tmp_path / 'main.cpp')
    work_dir = str(tmp_path)
    gpp = str(tmp_path / 'toolchain' / 'g++.exe')

    command, output = compiler.build_compile_command(
        source,
        'cpp',
        work_dir,
        {'g++': gpp},
    )

    assert command[0] == str(Path(gpp).resolve())
    assert command[-1] == '-std=c++17'
    assert Path(output).parent == Path(work_dir).resolve()
    assert compiler.compile_uses_shell is False


def test_unknown_language_has_no_command():
    compiler = Compiler()

    with pytest.raises(ValueError, match='Unsupported language'):
        compiler.build_compile_command('main.txt', 'ruby', '.', {})
