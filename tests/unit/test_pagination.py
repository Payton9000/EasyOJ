from app.utils.pagination import parse_pagination


def test_pagination_clamps_invalid_and_large_values():
    assert parse_pagination({'page': '-3', 'per_page': '10000'}) == (1, 100)
    assert parse_pagination({'page': '2', 'per_page': '25'}) == (2, 25)
