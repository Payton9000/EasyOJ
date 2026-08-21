from pathlib import Path
from types import SimpleNamespace

from app.judge.compiler import Compiler
from app.judge.executor import Executor


def _custom_app(tmp_path):
    root = Path(tmp_path)
    rustc = root / 'toolchain' / 'rust' / 'rustc.exe'
    return SimpleNamespace(
        config={
            'SUPPORTED_LANGUAGES': {
                'rust': {
                    'name': 'Rust',
                    'source_file': 'main.rs',
                    'compiler_key': 'rustc',
                    'compile_args': ['{source}', '-o', '{output}'],
                    'output_name': 'main.exe',
                    'run_args': ['{executable}'],
                },
            },
            'COMPILER_PATHS': {'rustc': str(rustc)},
        }
    )


def test_custom_language_can_define_vector_commands_without_shell(tmp_path):
    app = _custom_app(tmp_path)
    compiler = Compiler(app)
    command, output = compiler.build_compile_command(
        str(tmp_path / 'main.rs'), 'rust', str(tmp_path), app.config['COMPILER_PATHS']
    )
    run_command = Executor(app).build_run_command(str(tmp_path), 'rust')

    assert command[0] == str((tmp_path / 'toolchain' / 'rust' / 'rustc.exe').resolve())
    assert command[-2:] == ['-o', str((tmp_path / 'main.exe').resolve())]
    assert output == str((tmp_path / 'main.exe').resolve())
    assert run_command == [str((tmp_path / 'main.exe').resolve())]


def test_custom_language_source_filename_is_used(tmp_path):
    app = _custom_app(tmp_path)

    import app.utils.file_utils as file_utils

    # The registry-backed filename helper is exercised through the configured app.
    with app_context_stub(app):
        assert file_utils.language_source_filename('rust') == 'main.rs'


def test_java_run_command_bounds_jvm_memory_and_parallelism(tmp_path):
    from app.judge.languages import build_run_command

    config = {
        'SUPPORTED_LANGUAGES': {
            'java': {
                'source_file': 'Main.java',
                'run_tool_key': 'java',
                'run_args': ['{runtime}', '-cp', '{classpath}', 'Main'],
            }
        },
        'COMPILER_PATHS': {'java': str(tmp_path / 'java.exe')},
    }

    command = build_run_command(
        config,
        str(tmp_path),
        'java',
        config['COMPILER_PATHS'],
        memory_limit_mb=256,
    )

    assert command[0] == str((tmp_path / 'java.exe').resolve())
    assert '-Xmx179m' in command
    assert '-XX:ActiveProcessorCount=1' in command
    assert '-XX:+UseSerialGC' in command


class app_context_stub:
    def __init__(self, app):
        self.app = app

    def __enter__(self):
        from flask import Flask

        self.flask_app = Flask('language-test')
        self.flask_app.config.update(self.app.config)
        self.context = self.flask_app.app_context()
        self.context.push()
        return self

    def __exit__(self, *exc):
        self.context.pop()
