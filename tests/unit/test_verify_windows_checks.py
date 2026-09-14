from scripts.verify_windows import classroom_check_names


def test_safe_mode_skips_developer_linters_and_pytest():
    names = classroom_check_names(dev=False)

    assert 'toolchain' in names
    assert 'sandbox' in names
    assert 'ruff-check' not in names
    assert 'ruff-format' not in names
    assert 'pytest' not in names


def test_dev_mode_includes_ruff_and_pytest():
    names = classroom_check_names(dev=True)

    assert names == [
        'compileall',
        'ruff-check',
        'ruff-format',
        'pytest',
        'toolchain',
        'sandbox',
    ]
