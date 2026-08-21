from collections import Counter

from problem_bank.packs.arrays_strings import get_specs
from problem_bank.validation import validate_catalog


def _spec_by_title(title):
    return next(spec for spec in get_specs() if spec.title == title)


def test_pack_has_exact_problem_count_and_difficulty_distribution():
    specs = get_specs()

    assert isinstance(specs, tuple)
    assert len(specs) == 7
    assert Counter(spec.difficulty for spec in specs) == {'easy': 3, 'medium': 4}
    assert len({spec.title.casefold() for spec in specs}) == 7


def test_pack_is_valid_and_uses_real_newlines_in_all_case_inputs():
    specs = get_specs()
    validate_catalog(specs)
    literal_escape = chr(92) + 'n'

    assert all(len(spec.cases) >= 10 for spec in specs)
    assert all('\n' in spec.sample_output for spec in specs)
    assert all('\n' in case.input_data for spec in specs for case in spec.cases)
    assert all('\n' in case.expected_output for spec in specs for case in spec.cases)
    assert all(
        literal_escape not in text
        for spec in specs
        for text in (
            spec.sample_input,
            spec.sample_output,
            *(case.input_data for case in spec.cases),
            *(case.expected_output for case in spec.cases),
        )
    )


def test_representative_cases_have_literal_expected_answers():
    representatives = {
        'Lone Number in Pairs': ('5\n1 2 1 2 9\n', '9\n'),
        'Longest Uniform Streak': ('aabbbccccaa\n', '4\n'),
        'Vowel-Edge Words': ('5\narea\neerie\notto\nunit\nubuntu\n', '4\n'),
        'Sorted Pair Target Count': ('8 10\n1 1 2 3 7 8 9 9\n', '6\n'),
        'Smallest Pattern Window': ('adobecodebanc\nabc\n', '4\n'),
        'Balance Index': ('5\n-1 -1 0 -1 -1\n', '3\n'),
        'Labeled Amount Query': ('5\nred 4\nblue 9\nred -1\ngreen 8\nred 3\nred\n', '6\n'),
    }

    for title, (input_data, expected_output) in representatives.items():
        spec = _spec_by_title(title)
        assert (
            next(case for case in spec.cases if case.input_data == input_data).expected_output
            == expected_output
        )


def test_smallest_pattern_window_has_a_verified_boundary_case():
    spec = _spec_by_title('Smallest Pattern Window')

    case = next(case for case in spec.cases if case.input_data == 'abcdebdde\nbce\n')

    assert case.expected_output == '4\n'
