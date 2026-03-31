import logging
import os
import shutil
import time

logger = logging.getLogger(__name__)

# Resolve base directory relative to this file's location:
# OJ_System/app/utils/file_utils.py -> OJ_System/
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

FILE_EXTENSION = {
    'cpp': 'main.cpp',
    'java': 'Main.java',
    'python': 'main.py',
}


def _base_dir():
    try:
        from flask import current_app
        return current_app.config.get('BASE_DIR', _BASE_DIR)
    except RuntimeError:
        return _BASE_DIR


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def create_judge_workspace(submission_id):
    temp_dir = os.path.join(_base_dir(), 'data', 'temp')
    ensure_dir(temp_dir)
    workspace_name = f'judge_{submission_id}_{int(time.time() * 1000)}'
    workspace = os.path.join(temp_dir, workspace_name)
    ensure_dir(workspace)
    return os.path.abspath(workspace)


def cleanup_dir(path):
    temp_dir = os.path.abspath(os.path.join(_base_dir(), 'data', 'temp'))
    abs_path = os.path.abspath(path)
    if not abs_path.startswith(temp_dir + os.sep) and abs_path != temp_dir:
        logger.error('Refusing to delete path outside data/temp: %s', abs_path)
        return
    try:
        shutil.rmtree(abs_path)
    except Exception as e:
        logger.error('Failed to cleanup directory %s: %s', abs_path, e)


def write_code_file(work_dir, code, language):
    filename = FILE_EXTENSION.get(language, 'main.txt')
    file_path = os.path.join(work_dir, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(code)
    return os.path.abspath(file_path)


def load_test_cases(problem_id):
    tc_dir = os.path.join(_base_dir(), 'data', 'problems', str(problem_id), 'testcases')
    if not os.path.isdir(tc_dir):
        return []
    in_files = [f for f in os.listdir(tc_dir) if f.endswith('.in')]
    if not in_files:
        return []
    try:
        in_files.sort(key=lambda x: int(os.path.splitext(x)[0]))
    except ValueError:
        in_files.sort()
    result = []
    for in_file in in_files:
        num = os.path.splitext(in_file)[0]
        out_file = num + '.out'
        in_path = os.path.join(tc_dir, in_file)
        out_path = os.path.join(tc_dir, out_file)
        if not os.path.isfile(out_path):
            continue
        with open(in_path, 'r', encoding='utf-8') as f:
            input_data = f.read()
        with open(out_path, 'r', encoding='utf-8') as f:
            expected_output = f.read()
        result.append((input_data, expected_output))
    return result


def get_problem_dir(problem_id):
    return os.path.abspath(os.path.join(_base_dir(), 'data', 'problems', str(problem_id)))


def get_submission_dir(submission_id):
    return os.path.abspath(os.path.join(_base_dir(), 'data', 'submissions', str(submission_id)))
