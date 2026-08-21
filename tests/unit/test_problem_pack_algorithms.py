from collections import Counter

from problem_bank.packs.algorithms import _connected_treasure_cells
from problem_bank.packs.algorithms import _edit_distance
from problem_bank.packs.algorithms import _first_beacon
from problem_bank.packs.algorithms import _knight_distance
from problem_bank.packs.algorithms import _largest_window_sum
from problem_bank.packs.algorithms import _minimum_cost_climb
from problem_bank.packs.algorithms import _minimum_recharge_stops
from problem_bank.packs.algorithms import _numbers
from problem_bank.packs.algorithms import _range_increment
from problem_bank.packs.algorithms import get_specs
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


def test_algorithms_pack_has_eight_valid_original_specs():
    specs = get_specs()

    assert isinstance(specs, tuple)
    assert len(specs) == 8
    assert Counter(spec.difficulty for spec in specs) == Counter(medium=6, hard=2)
    assert len({spec.title.casefold() for spec in specs}) == 8
    assert not SEED_TITLES.intersection(spec.title for spec in specs)

    validate_catalog(specs)

    literal_escape = chr(92) + 'n'
    for spec in specs:
        assert 1 <= spec.time_limit <= 20000
        assert 1 <= spec.memory_limit <= 512
        assert '\n' in spec.sample_input
        assert literal_escape not in spec.sample_input
        assert literal_escape not in spec.sample_output
        assert all('\n' in case.input_data for case in spec.cases)
        assert all(literal_escape not in case.input_data for case in spec.cases)
        assert all(literal_escape not in case.expected_output for case in spec.cases)


def test_algorithms_pack_representative_answers_are_literal_and_correct():
    specs = {spec.title: spec for spec in get_specs()}

    assert specs['First Beacon At Or Above'].sample_output == '3\n'
    assert specs['Minimum Recharge Stops'].sample_output == '2\n'
    assert specs['Range Increment Heights'].sample_output == '4 7 8 6\n'
    assert specs['Largest Sum Window'].sample_output == '12\n'
    assert specs['Connected Treasure Cells'].sample_output == '7\n'
    assert specs["Knight's Shortest Escape"].sample_output == '2\n'
    assert specs['Minimum Cost Climb'].sample_output == '12\n'
    assert specs['Edit Distance Lite'].sample_output == '3\n'


def test_every_sample_matches_its_reference_generated_case():
    for spec in get_specs():
        assert spec.sample_input == spec.cases[0].input_data, spec.title
        assert spec.sample_output == spec.cases[0].expected_output, spec.title


def _reference_output(spec, input_data):
    lines = input_data.splitlines()
    if spec.title == 'First Beacon At Or Above':
        _, target = map(int, lines[0].split())
        result = _first_beacon(list(map(int, lines[1].split())), target)
    elif spec.title == 'Minimum Recharge Stops':
        distance, tank, _ = map(int, lines[0].split())
        stations = list(map(int, lines[1].split()))
        result = _minimum_recharge_stops(distance, tank, stations)
    elif spec.title == 'Range Increment Heights':
        _, update_count = map(int, lines[0].split())
        values = list(map(int, lines[1].split()))
        updates = [tuple(map(int, line.split())) for line in lines[2 : 2 + update_count]]
        result = _numbers(_range_increment(values, updates))
    elif spec.title == 'Largest Sum Window':
        _, width = map(int, lines[0].split())
        result = _largest_window_sum(list(map(int, lines[1].split())), width)
    elif spec.title == 'Connected Treasure Cells':
        row_count, _ = map(int, lines[0].split())
        result = _connected_treasure_cells(lines[1 : 1 + row_count])
    elif spec.title == "Knight's Shortest Escape":
        result = _knight_distance(*map(int, lines[0].split()))
    elif spec.title == 'Minimum Cost Climb':
        result = _minimum_cost_climb(list(map(int, lines[1].split())))
    else:
        result = _edit_distance(lines[0], lines[1])
    return f'{result}\n'


def test_every_case_matches_its_focused_reference_function():
    for spec in get_specs():
        for case in spec.cases:
            assert case.expected_output == _reference_output(spec, case.input_data), spec.title
