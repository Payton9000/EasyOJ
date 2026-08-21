import logging
import os
import shutil
import stat
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Resolve base directory relative to this file's location:
# OJ_System/app/utils/file_utils.py -> OJ_System/
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

FILE_EXTENSION = {
    'cpp': 'main.cpp',
    'java': 'Main.java',
    'python': 'main.py',
}

TESTCASE_LIMIT_KEYS = (
    'TESTCASE_MAX_INPUT_BYTES',
    'TESTCASE_MAX_OUTPUT_BYTES',
    'TESTCASE_MAX_COUNT',
    'TESTCASE_MAX_PROBLEM_BYTES',
    'TESTCASE_MAX_GLOBAL_BYTES',
    'TESTCASE_MIN_FREE_SPACE_BYTES',
    'TESTCASE_UPLOAD_CHUNK_BYTES',
)


class TestcaseDataError(ValueError):
    """Raised when stored test data is missing, malformed, or unsafe."""


class TestcaseUploadError(TestcaseDataError):
    """Raised when an upload cannot be accepted within the configured policy."""


@dataclass(frozen=True)
class TestcaseFile:
    number: int
    input_path: str
    output_path: str
    input_size: int
    output_size: int


def language_source_filename(language):
    try:
        from flask import current_app

        config = current_app.config
    except RuntimeError:
        config = {'SUPPORTED_LANGUAGES': {}}

    from app.judge.languages import source_filename

    try:
        return source_filename(config, language)
    except ValueError:
        if language in FILE_EXTENSION:
            return FILE_EXTENSION[language]
        raise


def _base_dir():
    try:
        from flask import current_app

        return current_app.config.get('BASE_DIR', _BASE_DIR)
    except RuntimeError:
        return _BASE_DIR


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def testcase_limits(config=None):
    """Return validated testcase limits, failing closed on missing settings."""
    if config is None:
        try:
            from flask import current_app

            config = current_app.config
        except RuntimeError as exc:
            raise TestcaseDataError('testcase limits require an application config') from exc
    result = {}
    for key in TESTCASE_LIMIT_KEYS:
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TestcaseDataError(f'invalid testcase limit: {key}')
        if value <= 0 and key != 'TESTCASE_MIN_FREE_SPACE_BYTES':
            raise TestcaseDataError(f'invalid testcase limit: {key}')
        if value < 0:
            raise TestcaseDataError(f'invalid testcase limit: {key}')
        result[key] = value
    return result


def validate_upload_filename(filename, extension):
    """Reject client-supplied path components and require one exact extension."""
    if not isinstance(filename, str) or not filename or '\x00' in filename:
        raise TestcaseUploadError('invalid upload filename')
    normalized = filename.replace('\\', '/')
    if '/' in normalized or normalized in {'.', '..'} or not normalized.lower().endswith(extension):
        raise TestcaseUploadError('invalid upload filename')
    stem = normalized[: -len(extension)]
    if not stem or stem in {'.', '..'}:
        raise TestcaseUploadError('invalid upload filename')
    return normalized


def _is_reparse_or_symlink(path, stat_result=None):
    try:
        stat_result = stat_result or os.lstat(path)
    except OSError as exc:
        raise TestcaseDataError(f'cannot inspect testcase path: {path}') from exc
    if stat.S_ISLNK(stat_result.st_mode) or os.path.islink(path):
        return True
    # FILE_ATTRIBUTE_REPARSE_POINT, present on Windows lstat results.
    return bool(getattr(stat_result, 'st_file_attributes', 0) & 0x400)


def _require_regular_file(path):
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise TestcaseDataError(f'cannot inspect testcase file: {path}') from exc
    if _is_reparse_or_symlink(path, info) or not stat.S_ISREG(info.st_mode):
        raise TestcaseDataError(f'unsafe testcase file: {path}')
    return info


def _testcase_dir(problem_id, base_dir=None):
    root = base_dir or _base_dir()
    return os.path.abspath(os.path.join(root, 'data', 'problems', str(problem_id), 'testcases'))


def validate_testcase_directory(testcase_dir):
    """Reject links in the storage path before any directory is created."""
    testcase_dir = os.path.abspath(testcase_dir)
    base_dir = os.path.abspath(os.path.join(testcase_dir, '..', '..', '..', '..'))
    paths = (
        os.path.join(base_dir, 'data'),
        os.path.join(base_dir, 'data', 'problems'),
        os.path.dirname(testcase_dir),
        testcase_dir,
    )
    for path in paths:
        if os.path.lexists(path) and (_is_reparse_or_symlink(path) or not os.path.isdir(path)):
            raise TestcaseDataError(f'unsafe testcase directory: {path}')


def _scan_testcase_files(
    testcase_dir,
    limits,
    *,
    enforce_file_limits=True,
    enforce_quotas=True,
):
    validate_testcase_directory(testcase_dir)
    if not os.path.lexists(testcase_dir):
        return []
    if _is_reparse_or_symlink(testcase_dir) or not os.path.isdir(testcase_dir):
        raise TestcaseDataError(f'unsafe testcase directory: {testcase_dir}')

    names = []
    try:
        names = os.listdir(testcase_dir)
    except OSError as exc:
        raise TestcaseDataError(f'cannot list testcase directory: {testcase_dir}') from exc
    pairs = {}
    for name in names:
        lower = name.lower()
        if not (lower.endswith('.in') or lower.endswith('.out')):
            continue
        extension = '.in' if lower.endswith('.in') else '.out'
        validate_upload_filename(name, extension)
        stem = name[: -len(extension)]
        if not stem.isdigit() or int(stem) <= 0:
            raise TestcaseDataError(f'invalid testcase number: {name}')
        path = os.path.join(testcase_dir, name)
        info = _require_regular_file(path)
        limit_key = (
            'TESTCASE_MAX_INPUT_BYTES' if extension == '.in' else 'TESTCASE_MAX_OUTPUT_BYTES'
        )
        if enforce_file_limits and info.st_size > limits[limit_key]:
            raise TestcaseDataError(f'testcase file exceeds limit: {name}')
        pairs.setdefault(int(stem), {})[extension] = (path, info.st_size)

    result = []
    for number in sorted(pairs):
        pair = pairs[number]
        if '.in' not in pair or '.out' not in pair:
            raise TestcaseDataError(f'missing matching testcase file: {number}')
        result.append(
            TestcaseFile(
                number,
                pair['.in'][0],
                pair['.out'][0],
                pair['.in'][1],
                pair['.out'][1],
            )
        )
    if enforce_quotas and len(result) > limits['TESTCASE_MAX_COUNT']:
        raise TestcaseDataError('testcase count exceeds limit')
    if enforce_quotas and (
        sum(case.input_size + case.output_size for case in result)
        > limits['TESTCASE_MAX_PROBLEM_BYTES']
    ):
        raise TestcaseDataError('problem testcase quota exceeded')
    return result


def _iter_problem_dirs(base_dir):
    problems_dir = os.path.join(base_dir, 'data', 'problems')
    if not os.path.lexists(problems_dir):
        return []
    if _is_reparse_or_symlink(problems_dir) or not os.path.isdir(problems_dir):
        raise TestcaseDataError(f'unsafe problems directory: {problems_dir}')
    result = []
    for name in os.listdir(problems_dir):
        path = os.path.join(problems_dir, name)
        if not name.isdigit():
            continue
        if _is_reparse_or_symlink(path) or not os.path.isdir(path):
            raise TestcaseDataError(f'unsafe problem directory: {path}')
        result.append(path)
    return result


def testcase_storage_usage(base_dir=None, config=None):
    limits = testcase_limits(config)
    root = base_dir or _base_dir()
    total = 0
    for problem_dir in _iter_problem_dirs(root):
        testcase_dir = os.path.join(problem_dir, 'testcases')
        for case in _scan_testcase_files(
            testcase_dir,
            limits,
            enforce_file_limits=False,
            enforce_quotas=False,
        ):
            total += case.input_size + case.output_size
    if total > limits['TESTCASE_MAX_GLOBAL_BYTES']:
        raise TestcaseDataError('global testcase quota exceeded')
    return total


def available_disk_bytes(path):
    try:
        disk_path = path if os.path.exists(path) else os.path.dirname(path)
        return shutil.disk_usage(disk_path).free
    except OSError as exc:
        raise TestcaseUploadError('cannot determine available disk space') from exc


def validate_testcase_storage(problem_id, config=None, base_dir=None):
    """Validate an existing problem and global store after publication."""
    limits = testcase_limits(config)
    root = base_dir or _base_dir()
    testcase_dir = _testcase_dir(problem_id, root)
    cases = _scan_testcase_files(testcase_dir, limits, enforce_file_limits=False)
    usage = testcase_storage_usage(root, limits)
    if available_disk_bytes(testcase_dir) < limits['TESTCASE_MIN_FREE_SPACE_BYTES']:
        raise TestcaseUploadError('minimum free disk space would be violated')
    return cases, usage


def validate_testcase_upload(problem_id, input_size, output_size, config=None, base_dir=None):
    """Validate a new pair before it is published."""
    limits = testcase_limits(config)
    if any(
        isinstance(size, bool) or not isinstance(size, int) for size in (input_size, output_size)
    ):
        raise TestcaseUploadError('invalid testcase size')
    if input_size > limits['TESTCASE_MAX_INPUT_BYTES']:
        raise TestcaseUploadError('input testcase file exceeds limit')
    if output_size > limits['TESTCASE_MAX_OUTPUT_BYTES']:
        raise TestcaseUploadError('output testcase file exceeds limit')
    if input_size < 0 or output_size < 0:
        raise TestcaseUploadError('invalid testcase size')
    root = base_dir or _base_dir()
    testcase_dir = _testcase_dir(problem_id, root)
    existing = _scan_testcase_files(testcase_dir, limits, enforce_file_limits=False)
    existing_problem_bytes = sum(case.input_size + case.output_size for case in existing)
    if len(existing) + 1 > limits['TESTCASE_MAX_COUNT']:
        raise TestcaseUploadError('testcase count limit reached')
    incoming = input_size + output_size
    if existing_problem_bytes + incoming > limits['TESTCASE_MAX_PROBLEM_BYTES']:
        raise TestcaseUploadError('problem testcase quota reached')
    if testcase_storage_usage(root, limits) + incoming > limits['TESTCASE_MAX_GLOBAL_BYTES']:
        raise TestcaseUploadError('global testcase quota reached')
    if available_disk_bytes(testcase_dir) < limits['TESTCASE_MIN_FREE_SPACE_BYTES'] + incoming:
        raise TestcaseUploadError('insufficient free disk space')
    return limits


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
    filename = language_source_filename(language)
    file_path = os.path.join(work_dir, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(code)
    return os.path.abspath(file_path)


def iter_testcase_files(problem_id):
    limits = testcase_limits()
    yield from _scan_testcase_files(_testcase_dir(problem_id), limits)


def iter_test_cases(problem_id):
    """Yield one decoded testcase pair at a time, without retaining all cases."""
    for case in iter_testcase_files(problem_id):
        try:
            with open(case.input_path, encoding='utf-8') as input_file:
                input_data = input_file.read()
            with open(case.output_path, encoding='utf-8') as output_file:
                expected_output = output_file.read()
        except (OSError, UnicodeError) as exc:
            raise TestcaseDataError(f'cannot read testcase {case.number}') from exc
        yield input_data, expected_output


def load_test_cases(problem_id):
    return list(iter_test_cases(problem_id))


def count_test_cases(problem_id):
    return sum(1 for _ in iter_testcase_files(problem_id))


def get_problem_dir(problem_id):
    return os.path.abspath(os.path.join(_base_dir(), 'data', 'problems', str(problem_id)))


def get_submission_dir(submission_id):
    return os.path.abspath(os.path.join(_base_dir(), 'data', 'submissions', str(submission_id)))
