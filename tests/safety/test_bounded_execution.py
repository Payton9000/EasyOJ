import pytest

from tests.load.safe_load_test import validate_options


def test_safe_load_rejects_unbounded_values():
    with pytest.raises(ValueError):
        validate_options(duration=31, users=4, workers=2, max_requests=20)
    with pytest.raises(ValueError):
        validate_options(duration=10, users=13, workers=2, max_requests=20)
    with pytest.raises(ValueError):
        validate_options(duration=10, users=4, workers=3, max_requests=20)
    with pytest.raises(ValueError):
        validate_options(duration=10, users=4, workers=2, max_requests=101)


def test_safe_load_accepts_small_default_shape():
    validate_options(duration=10, users=4, workers=2, max_requests=20)
