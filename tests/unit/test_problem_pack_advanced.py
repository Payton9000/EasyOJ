from collections import Counter

from problem_bank.packs.advanced import get_specs
from problem_bank.validation import validate_catalog

SEED_TITLES = {
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


def test_advanced_pack_has_eight_valid_hard_original_specs():
    specs = get_specs()

    assert isinstance(specs, tuple)
    assert len(specs) == 8
    assert Counter(spec.difficulty for spec in specs) == Counter(hard=8)
    assert len({spec.title.casefold() for spec in specs}) == 8
    assert not SEED_TITLES.intersection(spec.title for spec in specs)

    validate_catalog(specs)

    literal_escape = chr(92) + 'n'
    for spec in specs:
        assert 1 <= spec.time_limit <= 20000
        assert 1 <= spec.memory_limit <= 512
        assert '\n' in spec.sample_input
        assert '\n' in spec.sample_output
        assert literal_escape not in spec.sample_input
        assert literal_escape not in spec.sample_output
        assert len(spec.cases) >= 10
        assert all('\n' in case.input_data for case in spec.cases)
        assert all(literal_escape not in case.input_data for case in spec.cases)
        assert all(literal_escape not in case.expected_output for case in spec.cases)


def test_advanced_pack_has_hand_checked_representative_answers():
    specs = {spec.title: spec for spec in get_specs()}

    assert specs['Critical Road Bridges'].sample_output == '2\n'
    assert specs['Rerooted Tree Distance Totals'].sample_output == '6 4 4 6\n'
    assert specs['Weighted Interval Revenue'].sample_output == '17\n'
    assert specs['Minimum Palindrome Cuts'].sample_output == '1\n'
    assert specs['Dynamic Range Minimum'].sample_output == '1\n2\n-3\n'
    assert specs['Sliding Median Total'].sample_output == '15\n'
    assert specs['Exact Nonempty Groupings'].sample_output == '15\n'
    assert specs['Kth Balanced Parentheses'].sample_output == '()(())\n'
