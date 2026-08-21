import importlib

import pytest


def _parse_pagination():
    try:
        return importlib.import_module('app.utils.pagination').parse_pagination
    except (ImportError, AttributeError) as exc:
        pytest.fail(f'pagination helper is not implemented yet: {exc}')


def test_pagination_clamps_invalid_and_large_values():
    parse = _parse_pagination()

    assert parse({'page': '-3', 'per_page': '10000'}) == (1, 100)
    assert parse({'page': '2', 'per_page': '25'}) == (2, 25)
