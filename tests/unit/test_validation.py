import importlib

import pytest


def _validation_module():
    try:
        return importlib.import_module('app.utils.validation')
    except ModuleNotFoundError as exc:
        pytest.fail(f'validation module is not implemented yet: {exc}')


def test_username_is_trimmed_and_normalized():
    validation = _validation_module()

    assert validation.validate_username('  Student_01  ') == 'student_01'


@pytest.mark.parametrize('value', ['', 'ab', 'has space', '管理员', 'a/b', 'x' * 33])
def test_username_rejects_unsafe_or_invalid_values(value):
    validation = _validation_module()

    with pytest.raises(ValueError):
        validation.validate_username(value)


def test_email_is_trimmed_and_lowercased():
    validation = _validation_module()

    assert validation.validate_email('  Student@Example.COM ') == 'student@example.com'


@pytest.mark.parametrize('value', ['', 'not-an-email', 'a@', '@example.com', 'x' * 121 + '@x.com'])
def test_email_rejects_invalid_values(value):
    validation = _validation_module()

    with pytest.raises(ValueError):
        validation.validate_email(value)


def test_password_policy_accepts_eight_characters():
    validation = _validation_module()

    assert validation.validate_password('abc12345') == 'abc12345'


def test_password_policy_rejects_short_passwords():
    validation = _validation_module()

    with pytest.raises(ValueError):
        validation.validate_password('abc1234')
