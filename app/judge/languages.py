"""Configurable language command registry.

Language definitions contain only argument vectors.  Commands are never
joined into a shell string, so adding a language does not reintroduce shell
injection through a compiler configuration.
"""

from __future__ import annotations

import os

DEFAULT_LANGUAGE_SPECS = {
    'cpp': {
        'name': 'C++',
        'source_file': 'main.cpp',
        'compiler_key': 'g++',
        'compile_args': ['{source}', '-o', '{output}', '-O2', '-std=c++17'],
        'output_name': 'main.exe',
        'run_args': ['{executable}'],
    },
    'java': {
        'name': 'Java',
        'source_file': 'Main.java',
        'compiler_key': 'javac',
        'compile_args': ['{source}'],
        'run_tool_key': 'java',
        'run_args': ['{runtime}', '-cp', '{classpath}', 'Main'],
    },
    'python': {
        'name': 'Python',
        'source_file': 'main.py',
        'interpreter_key': 'python',
        'compile_args': None,
        'run_args': ['{interpreter}', '{source}'],
    },
}


def _specs(config=None):
    if config:
        configured = config.get('SUPPORTED_LANGUAGES')
        if configured:
            return configured
    return DEFAULT_LANGUAGE_SPECS


def get_language_spec(config, language):
    spec = _specs(config).get(language)
    if not isinstance(spec, dict):
        raise ValueError(f'Unsupported language: {language}')
    return spec


def _render_args(args, values):
    if args is None:
        return []
    return [str(argument).format(**values) for argument in args]


def _absolute_tool(path):
    return os.path.abspath(path)


def _java_heap_mb(memory_limit_mb):
    try:
        limit = max(1, int(memory_limit_mb))
    except (TypeError, ValueError):
        limit = 256
    return max(8, int(limit * 0.70))


def _java_runtime_options(memory_limit_mb):
    heap_mb = _java_heap_mb(memory_limit_mb)
    initial_heap_mb = min(16, heap_mb)
    return [
        f'-Xms{initial_heap_mb}m',
        f'-Xmx{heap_mb}m',
        '-XX:MaxMetaspaceSize=64m',
        '-XX:ReservedCodeCacheSize=32m',
        '-XX:ActiveProcessorCount=1',
        '-XX:+UseSerialGC',
    ]


def build_compile_command(config, source_path, language, work_dir, compiler_paths=None):
    spec = get_language_spec(config, language)
    compiler_paths = compiler_paths or (config or {}).get('COMPILER_PATHS', {})
    source_path = os.path.abspath(source_path)
    work_dir = os.path.abspath(work_dir)
    compile_args = spec.get('compile_args')
    if not compile_args:
        return [], source_path

    compiler_key = spec.get('compiler_key', language)
    compiler = compiler_paths.get(compiler_key, compiler_key)
    output_name = spec.get('output_name')
    output = os.path.join(work_dir, output_name) if output_name else work_dir
    values = {
        'source': source_path,
        'output': output,
        'executable': output,
        'work_dir': work_dir,
        'classpath': work_dir,
        'compiler': _absolute_tool(compiler),
    }
    return [_absolute_tool(compiler), *_render_args(compile_args, values)], output


def build_run_command(config, work_dir, language, compiler_paths=None, memory_limit_mb=256):
    spec = get_language_spec(config, language)
    compiler_paths = compiler_paths or (config or {}).get('COMPILER_PATHS', {})
    work_dir = os.path.abspath(work_dir)
    source = os.path.join(work_dir, spec.get('source_file', f'{language}.txt'))
    output_name = spec.get('output_name')
    executable = os.path.join(work_dir, output_name) if output_name else source
    runtime_key = spec.get('run_tool_key')
    runtime = _absolute_tool(compiler_paths.get(runtime_key, runtime_key)) if runtime_key else ''
    interpreter_key = spec.get('interpreter_key')
    interpreter = (
        _absolute_tool(compiler_paths.get(interpreter_key, interpreter_key))
        if interpreter_key
        else ''
    )
    values = {
        'source': source,
        'output': executable,
        'executable': executable,
        'work_dir': work_dir,
        'classpath': work_dir,
        'runtime': runtime,
        'interpreter': interpreter,
        'memory_limit_mb': max(1, int(memory_limit_mb or 256)),
    }
    command = _render_args(spec.get('run_args'), values)
    if language == 'java' and command:
        # A JVM otherwise sizes itself from host RAM instead of the OJ limit.
        # Inject hard bounds even when an installation customizes run_args.
        command[1:1] = _java_runtime_options(memory_limit_mb)
    return command


def source_filename(config, language):
    spec = get_language_spec(config, language)
    filename = spec.get('source_file')
    if not filename:
        extension = spec.get('file_ext', '.txt')
        filename = f'main{extension if str(extension).startswith(".") else "." + str(extension)}'
    if os.path.basename(filename) != filename or filename in ('.', '..'):
        raise ValueError(f'Invalid source filename for language: {language}')
    return filename
