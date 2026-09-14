from collections import Counter

from problem_bank.packs.advanced import get_specs

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
