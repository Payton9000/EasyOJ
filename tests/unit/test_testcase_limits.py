from pathlib import Path

import pytest

from app.utils import file_utils


def _testcase_dir(app, problem_id=1):
    path = Path(app.config['BASE_DIR']) / 'data' / 'problems' / str(problem_id) / 'testcases'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_case(directory, number, input_data='1\n', output_data='1\n'):
    (directory / f'{number}.in').write_text(input_data, encoding='utf-8')
    (directory / f'{number}.out').write_text(output_data, encoding='utf-8')


def test_testcase_limits_are_present_for_classroom_deployment(app):
    assert app.config['TESTCASE_MAX_INPUT_BYTES'] == 4 * 1024 * 1024
    assert app.config['TESTCASE_MAX_OUTPUT_BYTES'] == 4 * 1024 * 1024
    assert app.config['TESTCASE_MAX_COUNT'] == 2000
    assert app.config['TESTCASE_MAX_PROBLEM_BYTES'] == 64 * 1024 * 1024
    assert app.config['TESTCASE_MAX_GLOBAL_BYTES'] == 512 * 1024 * 1024


def test_iter_test_cases_streams_pairs_and_load_keeps_legacy_list(app):
    directory = _testcase_dir(app, 11)
    _write_case(directory, 1, 'first\n', 'one\n')
    _write_case(directory, 2, 'second\n', 'two\n')

    with app.app_context():
        iterator = file_utils.iter_test_cases(11)
        assert iter(iterator) is iterator
        assert next(iterator) == ('first\n', 'one\n')
        assert next(iterator) == ('second\n', 'two\n')
        with pytest.raises(StopIteration):
            next(iterator)
        assert file_utils.load_test_cases(11) == [
            ('first\n', 'one\n'),
            ('second\n', 'two\n'),
        ]


def test_invalid_testcase_pair_fails_closed(app):
    directory = _testcase_dir(app, 12)
    (directory / '1.in').write_text('input', encoding='utf-8')

    with app.app_context():
        with pytest.raises(file_utils.TestcaseDataError, match='missing matching'):
            list(file_utils.iter_test_cases(12))


def test_path_like_testcase_name_is_rejected():
    with pytest.raises(file_utils.TestcaseUploadError, match='filename'):
        file_utils.validate_upload_filename(r'..\outside.in', '.in')


def test_missing_or_invalid_limits_fail_closed():
    with pytest.raises(file_utils.TestcaseDataError):
        file_utils.testcase_limits({'TESTCASE_MAX_INPUT_BYTES': 0})


def test_symlinked_testcase_file_is_rejected(tmp_path):
    config = {
        'TESTCASE_MAX_INPUT_BYTES': 10,
        'TESTCASE_MAX_OUTPUT_BYTES': 10,
        'TESTCASE_MAX_COUNT': 2,
        'TESTCASE_MAX_PROBLEM_BYTES': 30,
        'TESTCASE_MAX_GLOBAL_BYTES': 100,
        'TESTCASE_MIN_FREE_SPACE_BYTES': 0,
        'TESTCASE_UPLOAD_CHUNK_BYTES': 4096,
    }
    testcase_dir = tmp_path / 'data' / 'problems' / '1' / 'testcases'
    testcase_dir.mkdir(parents=True)
    target = tmp_path / 'outside.in'
    target.write_text('input', encoding='utf-8')
    try:
        (testcase_dir / '1.in').symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip('symlink creation is unavailable on this Windows account')
    (testcase_dir / '1.out').write_text('output', encoding='utf-8')

    with pytest.raises(file_utils.TestcaseDataError, match='unsafe testcase file'):
        file_utils.testcase_storage_usage(str(tmp_path), config)


def test_symlinked_problem_directory_is_rejected(tmp_path):
    config = {
        'TESTCASE_MAX_INPUT_BYTES': 10,
        'TESTCASE_MAX_OUTPUT_BYTES': 10,
        'TESTCASE_MAX_COUNT': 2,
        'TESTCASE_MAX_PROBLEM_BYTES': 30,
        'TESTCASE_MAX_GLOBAL_BYTES': 100,
        'TESTCASE_MIN_FREE_SPACE_BYTES': 0,
        'TESTCASE_UPLOAD_CHUNK_BYTES': 4096,
    }
    problems_dir = tmp_path / 'data' / 'problems'
    problems_dir.mkdir(parents=True)
    target = tmp_path / 'outside-problem'
    target.mkdir()
    try:
        (problems_dir / '2').symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('symlink creation is unavailable on this Windows account')

    with pytest.raises(file_utils.TestcaseDataError, match='unsafe problem directory'):
        file_utils.testcase_storage_usage(str(tmp_path), config)
