from problem_bank.packs.foundations import get_specs
from problem_bank.schema import ProblemSpec
from problem_bank.validation import validate_catalog

_SEED_TITLES = {
    'A+B Basic',
    'Max Of Three',
    'Palindrome String',
    'GCD Query',
    'Range Sum 1D',
    'Binary Search Position',
    'Knapsack Tiny',
    'Grid BFS Distance',
    'Interval Scheduling',
    'Topological Sort Count Zero',
    'Bracket Sequence Validate',
    'Modular Exponentiation',
    'Connected Components Count',
    'Longest Nondecreasing Subsequence',
    'Subarray Sum Equals K Count',
    'Matrix Border Sum',
}


def _by_title():
    return {spec.title: spec for spec in get_specs()}


def test_foundations_pack_has_seven_unique_easy_problems():
    specs = get_specs()

    assert len(specs) == 7
    assert all(isinstance(spec, ProblemSpec) for spec in specs)
    assert all(spec.difficulty == 'easy' for spec in specs)

    titles = [spec.title for spec in specs]
    assert len(set(titles)) == len(titles)
    assert not _SEED_TITLES.intersection(titles)


def test_foundations_pack_validates_and_uses_real_newlines():
    specs = get_specs()

    validate_catalog(specs)

    for spec in specs:
        assert spec.time_limit > 0
        assert spec.memory_limit > 0
        assert len(spec.cases) >= 10
        assert '\\n' not in spec.sample_input
        assert '\\n' not in spec.sample_output
        assert '\n' in spec.sample_input
        assert '\n' in spec.sample_output
        for case in spec.cases:
            assert '\\n' not in case.input_data
            assert '\\n' not in case.expected_output
            assert '\n' in case.input_data
            assert '\n' in case.expected_output


def test_foundations_pack_has_hand_checkable_representative_answers():
    specs = _by_title()

    representatives = {
        'Bill After Discount': ('100 15\n', '85\n'),
        'Days In Month': ('2024 2\n', '29\n'),
        'Sum From One To N': ('10\n', '55\n'),
        'Count Numbers With Seven': ('5\n7 17 28 70 9\n', '3\n'),
        'Temperature Zone': ('25\n', 'MILD\n'),
        'Traffic Light After Steps': ('RED\n4\n', 'GREEN\n'),
        'Left Rotate Array': ('5 2\n1 2 3 4 5\n', '3 4 5 1 2\n'),
    }

    for title, expected_case in representatives.items():
        assert expected_case in {
            (case.input_data, case.expected_output) for case in specs[title].cases
        }


def test_count_numbers_with_seven_sample_counts_exactly_three_matches():
    spec = _by_title()['Count Numbers With Seven']
    tokens = spec.sample_input.split()
    numbers = [int(token) for token in tokens[1:]]
    expected_count = sum('7' in str(abs(number)) for number in numbers)

    assert expected_count == 3
    assert spec.sample_output == f'{expected_count}\n'
    sample_case = next(case for case in spec.cases if case.input_data == spec.sample_input)
    assert sample_case.expected_output == f'{expected_count}\n'
