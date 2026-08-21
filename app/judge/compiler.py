import logging
import subprocess

from app.judge.languages import DEFAULT_LANGUAGE_SPECS
from app.judge.languages import build_compile_command as build_language_compile_command

logger = logging.getLogger(__name__)


class Compiler:
    compile_uses_shell = False

    def __init__(self, app=None):
        self.app = app

    def _get_config(self):
        if self.app:
            return self.app.config
        from flask import current_app

        return current_app.config

    def build_compile_command(self, source_path, language, work_dir, compiler_paths=None):
        try:
            config = self._get_config()
        except RuntimeError:
            config = {'SUPPORTED_LANGUAGES': DEFAULT_LANGUAGE_SPECS}
        if compiler_paths is None:
            compiler_paths = config.get('COMPILER_PATHS', {})
        return build_language_compile_command(
            config,
            source_path,
            language,
            work_dir,
            compiler_paths,
        )

    def compile(self, source_path, language, work_dir) -> dict:
        try:
            cfg = self._get_config()
            compiler_paths = cfg.get('COMPILER_PATHS', {})

            cmd, executable = self.build_compile_command(
                source_path, language, work_dir, compiler_paths
            )
            if language == 'python':
                return {'success': True, 'error': '', 'executable': source_path}

            if cfg.get('SANDBOX_ENABLED', True):
                from app.judge.sandbox import SandboxRunner
                from app.judge.sandbox import is_supported

                if not is_supported():
                    return {
                        'success': False,
                        'error': 'Sandbox is enabled but not supported on this host.',
                        'executable': '',
                    }
                result = SandboxRunner(cfg).run(
                    cmd,
                    work_dir,
                    '',
                    cfg.get('JUDGE_COMPILE_TIMEOUT_MS', 30000),
                    cfg.get('JUDGE_COMPILE_MEMORY_MB', 512),
                    compiler_paths,
                    language,
                )
                if result.get('status') == 'OK':
                    return {'success': True, 'error': '', 'executable': executable}
                return {
                    'success': False,
                    'error': result.get('error', 'Compilation failed'),
                    'executable': '',
                }

            if cfg.get('JUDGE_REQUIRE_SANDBOX', True):
                return {
                    'success': False,
                    'error': 'Sandbox is required and cannot be disabled for this environment.',
                    'executable': '',
                }

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=work_dir,
                shell=self.compile_uses_shell,
            )
            if result.returncode == 0:
                return {'success': True, 'error': '', 'executable': executable}
            return {'success': False, 'error': result.stderr, 'executable': ''}

        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Compilation timed out', 'executable': ''}
        except FileNotFoundError:
            return {
                'success': False,
                'error': 'Compiler not found. Please check configuration.',
                'executable': '',
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'executable': ''}
