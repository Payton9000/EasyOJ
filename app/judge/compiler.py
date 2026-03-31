import logging
import os
import subprocess

logger = logging.getLogger(__name__)


class Compiler:
    def __init__(self, app=None):
        self.app = app

    def _get_config(self):
        if self.app:
            return self.app.config
        from flask import current_app
        return current_app.config

    def compile(self, source_path, language, work_dir) -> dict:
        try:
            cfg = self._get_config()
            compiler_paths = cfg.get('COMPILER_PATHS', {})

            if language == 'cpp':
                gpp = compiler_paths.get('g++', 'g++')
                output_exe = os.path.join(work_dir, 'main.exe')
                cmd = [gpp, source_path, '-o', output_exe, '-O2', '-std=c++17']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    return {'success': True, 'error': '', 'executable': output_exe}
                return {'success': False, 'error': result.stderr, 'executable': ''}

            elif language == 'java':
                javac = compiler_paths.get('javac', 'javac')
                cmd = [javac, source_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    return {'success': True, 'error': '', 'executable': work_dir}
                return {'success': False, 'error': result.stderr, 'executable': ''}

            elif language == 'python':
                return {'success': True, 'error': '', 'executable': source_path}

            else:
                return {'success': False, 'error': f'Unknown language: {language}', 'executable': ''}

        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Compilation timed out', 'executable': ''}
        except FileNotFoundError:
            return {'success': False, 'error': 'Compiler not found. Please check configuration.',
                    'executable': ''}
        except Exception as e:
            return {'success': False, 'error': str(e), 'executable': ''}
