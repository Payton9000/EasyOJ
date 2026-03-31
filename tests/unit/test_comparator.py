from app.judge.comparator import Comparator


def test_compare_normalizes_whitespace():
    comp = Comparator()
    assert comp.compare('1 2\n3\n', '1 2\n3') is True
    assert comp.compare('1 2\n3\n\n', '1 2\n3') is True
    assert comp.compare('1 2\n4', '1 2\n3') is False


def test_compare_float_precision():
    comp = Comparator()
    assert comp.compare_float('1.000001', '1.000002', precision=5) is True
    assert comp.compare_float('1.0001', '1.0002', precision=5) is False
