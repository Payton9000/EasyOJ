from app.judge.comparator import Comparator


def test_compare_normalizes_whitespace():
    comp = Comparator()
    assert comp.compare('1 2\n3\n', '1 2\n3') is True
    assert comp.compare('1 2\n3\n\n', '1 2\n3') is True
    assert comp.compare('1 2\n4', '1 2\n3') is False


def test_compare_normalizes_line_endings_and_trailing_spaces():
    comp = Comparator()
    assert comp.compare('1 2\r\n3\r\n', '1 2\n3\n') is True
    assert comp.compare('1 2   \n3', '1 2\n3') is True
    # Leading whitespace inside the output is still significant.
    assert comp.compare('1 2\n   3', '1 2\n3') is False
