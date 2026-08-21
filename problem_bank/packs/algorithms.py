from bisect import bisect_left
from collections import deque

from problem_bank.schema import ProblemSpec
from problem_bank.schema import TestCase


def _numbers(values):
    return ' '.join(str(value) for value in values)


def _case(input_data, expected_output):
    return TestCase(input_data=input_data, expected_output=f'{expected_output}\n')


def _first_beacon(values, target):
    position = bisect_left(values, target)
    return position if position < len(values) else -1


def _minimum_recharge_stops(distance, tank, stations):
    stops = 0
    current = 0
    index = 0
    while current + tank < distance:
        furthest = current
        while index < len(stations) and stations[index] <= current + tank:
            furthest = stations[index]
            index += 1
        if furthest == current:
            return -1
        current = furthest
        stops += 1
    return stops


def _range_increment(values, updates):
    difference = [0] * (len(values) + 1)
    for left, right, delta in updates:
        difference[left - 1] += delta
        difference[right] -= delta

    result = []
    added = 0
    for index, value in enumerate(values):
        added += difference[index]
        result.append(value + added)
    return result


def _largest_window_sum(values, width):
    prefix = [0]
    for value in values:
        prefix.append(prefix[-1] + value)
    return max(prefix[index + width] - prefix[index] for index in range(len(values) - width + 1))


def _connected_treasure_cells(grid):
    rows = len(grid)
    columns = len(grid[0])
    start = next(
        (
            (row, column)
            for row in range(rows)
            for column in range(columns)
            if grid[row][column] == 'S'
        ),
        None,
    )
    if start is None:
        return 0

    visited = {start}
    queue = deque([start])
    while queue:
        row, column = queue.popleft()
        for row_delta, column_delta in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            next_row = row + row_delta
            next_column = column + column_delta
            if not (0 <= next_row < rows and 0 <= next_column < columns):
                continue
            if grid[next_row][next_column] == '#':
                continue
            position = (next_row, next_column)
            if position not in visited:
                visited.add(position)
                queue.append(position)
    return len(visited)


def _knight_distance(size, start_row, start_column, target_row, target_column):
    start = (start_row - 1, start_column - 1)
    target = (target_row - 1, target_column - 1)
    queue = deque([(start, 0)])
    visited = {start}
    moves = (
        (-2, -1),
        (-2, 1),
        (-1, -2),
        (-1, 2),
        (1, -2),
        (1, 2),
        (2, -1),
        (2, 1),
    )
    while queue:
        (row, column), distance = queue.popleft()
        if (row, column) == target:
            return distance
        for row_delta, column_delta in moves:
            next_row = row + row_delta
            next_column = column + column_delta
            position = (next_row, next_column)
            if not (0 <= next_row < size and 0 <= next_column < size):
                continue
            if position not in visited:
                visited.add(position)
                queue.append((position, distance + 1))
    return -1


def _minimum_cost_climb(costs):
    if len(costs) == 1:
        return costs[0]
    previous_two = costs[0]
    previous = min(costs[0] + costs[1], costs[1])
    for cost in costs[2:]:
        previous_two, previous = previous, cost + min(previous_two, previous)
    return previous


def _edit_distance(first, second):
    previous = list(range(len(second) + 1))
    for first_index, first_character in enumerate(first, 1):
        current = [first_index]
        for second_index, second_character in enumerate(second, 1):
            replacement = previous[second_index - 1] + (first_character != second_character)
            current.append(min(replacement, previous[second_index] + 1, current[-1] + 1))
        previous = current
    return previous[-1]


def _first_beacon_spec():
    raw_cases = (
        (7, 6, [1, 3, 4, 6, 6, 8, 10]),
        (4, -10, [-5, -2, 0, 7]),
        (5, 11, [1, 3, 5, 7, 9]),
        (1, 0, [0]),
        (6, 5, [5, 5, 5, 8, 12, 12]),
        (5, -1, [-8, -4, -1, 2, 9]),
        (8, 20, [-3, 0, 4, 4, 7, 13, 19, 19]),
        (3, 2, [2, 2, 2]),
        (6, 100, [10, 20, 30, 40, 50, 60]),
        (5, -100, [-20, -10, 0, 10, 20]),
    )
    cases = tuple(
        _case(f'{length} {target}\n{_numbers(values)}\n', _first_beacon(values, target))
        for length, target, values in raw_cases
    )
    return ProblemSpec(
        title='First Beacon At Or Above',
        difficulty='medium',
        time_limit=1000,
        memory_limit=128,
        source='binary search',
        description='Find the first beacon whose strength is at least the target strength.',
        input_description='The first line contains n and target. The second line contains n sorted strengths.',
        output_description='Print the zero-based index of the first qualifying beacon, or -1.',
        sample_input='7 6\n1 3 4 6 6 8 10\n',
        sample_output='3\n',
        cases=cases,
    )


def _recharge_spec():
    raw_cases = (
        (25, 10, [8, 15, 20]),
        (10, 10, []),
        (30, 10, [10, 20]),
        (31, 10, [9, 18, 27]),
        (50, 15, [12, 24, 36, 44]),
        (18, 7, [6, 12]),
        (40, 20, [19]),
        (100, 25, [20, 40, 60, 80]),
        (21, 10, [10]),
        (60, 12, [11, 22, 35, 47, 55]),
    )
    cases = tuple(
        _case(
            f'{distance} {tank} {len(stations)}\n{_numbers(stations)}\n',
            _minimum_recharge_stops(distance, tank, stations),
        )
        for distance, tank, stations in raw_cases
    )
    return ProblemSpec(
        title='Minimum Recharge Stops',
        difficulty='medium',
        time_limit=1500,
        memory_limit=128,
        source='greedy',
        description='Drive to the destination using the fewest station stops with a fixed tank range.',
        input_description='The first line contains distance, tank range, and station count. The second line lists station positions.',
        output_description='Print the minimum stops, or -1 if the destination cannot be reached.',
        sample_input='25 10 3\n8 15 20\n',
        sample_output='2\n',
        cases=cases,
    )


def _range_increment_spec():
    raw_cases = (
        ([1, 2, 3, 4], [(1, 1, 3), (2, 3, 5), (4, 4, 2)]),
        ([0, 0, 0], [(1, 3, 4)]),
        ([5], [(1, 1, -2)]),
        ([2, 4, 6, 8, 10], [(2, 5, 1), (1, 3, 2)]),
        ([-3, 0, 3, 6], [(1, 2, 5), (3, 4, -4)]),
        ([10, 10, 10, 10, 10, 10], [(3, 3, 7), (1, 6, -1)]),
        ([1, -1, 1, -1], [(2, 4, 3), (1, 1, 9)]),
        ([100, 200, 300], [(1, 2, -100), (2, 3, 50)]),
        ([7, 8, 9, 10, 11], [(4, 5, 5), (1, 4, -2), (2, 2, 10)]),
        ([-5, -4, -3, -2, -1], [(1, 5, 1), (2, 4, 2)]),
    )
    cases = []
    for values, updates in raw_cases:
        lines = [f'{len(values)} {len(updates)}', _numbers(values)]
        lines.extend(f'{left} {right} {delta}' for left, right, delta in updates)
        result = _range_increment(values, updates)
        cases.append(_case('\n'.join(lines) + '\n', _numbers(result)))
    return ProblemSpec(
        title='Range Increment Heights',
        difficulty='medium',
        time_limit=1500,
        memory_limit=128,
        source='difference array',
        description='Apply inclusive range increments and report every final height.',
        input_description='The first line contains n and q, followed by n heights and q lines of l r delta.',
        output_description='Print the n final heights in one line.',
        sample_input='4 3\n1 2 3 4\n1 1 3\n2 3 5\n4 4 2\n',
        sample_output='4 7 8 6\n',
        cases=tuple(cases),
    )


def _largest_window_spec():
    raw_cases = (
        (6, 3, [2, 5, 1, 6, 3, 2]),
        (1, 1, [9]),
        (5, 2, [-5, -2, -7, -1, -3]),
        (6, 4, [1, 2, 3, 4, 5, 6]),
        (7, 3, [10, -5, 4, -2, 8, -1, 3]),
        (4, 4, [0, 0, 0, 0]),
        (8, 5, [3, 3, 3, -10, 3, 3, 3, 3]),
        (3, 2, [100, -1, 100]),
        (5, 3, [-1, -1, -1, -1, 20]),
        (9, 1, [-4, 2, 0, 7, -3, 5, -9, 8, 1]),
    )
    cases = tuple(
        _case(f'{length} {width}\n{_numbers(values)}\n', _largest_window_sum(values, width))
        for length, width, values in raw_cases
    )
    return ProblemSpec(
        title='Largest Sum Window',
        difficulty='medium',
        time_limit=1500,
        memory_limit=128,
        source='prefix sums',
        description='Find the largest sum among all contiguous windows of one fixed width.',
        input_description='The first line contains n and window width k. The second line contains n integers.',
        output_description='Print the largest sum of exactly k consecutive integers.',
        sample_input='6 3\n2 5 1 6 3 2\n',
        sample_output='12\n',
        cases=cases,
    )


def _treasure_spec():
    raw_cases = (
        ['S..', '.##', '...'],
        ['S#.', '...', '.#.'],
        [
            'S',
        ],
        ['S#', '#.'],
        ['S...', '....', '...#'],
        ['S..#', '.#..', '..#.'],
        ['S#..#', '.#.#.', '...#.'],
        ['S...', '####', '....'],
        ['S.#.', '..#.', '...#', '#...'],
        ['S..', '..#', '#..', '..#'],
    )
    cases = tuple(
        _case(
            f'{len(grid)} {len(grid[0])}\n{chr(10).join(grid)}\n', _connected_treasure_cells(grid)
        )
        for grid in raw_cases
    )
    return ProblemSpec(
        title='Connected Treasure Cells',
        difficulty='medium',
        time_limit=1500,
        memory_limit=128,
        source='graph traversal',
        description='Count cells reachable from S by four-direction moves through non-wall cells.',
        input_description='The first line contains rows and columns, followed by a grid using S, ., and #.',
        output_description='Print the number of reachable cells, including S.',
        sample_input='3 3\nS..\n.##\n...\n',
        sample_output='7\n',
        cases=cases,
    )


def _knight_spec():
    raw_cases = (
        (5, 1, 1, 4, 4),
        (1, 1, 1, 1, 1),
        (2, 1, 1, 2, 2),
        (8, 1, 1, 8, 8),
        (10, 3, 3, 8, 9),
        (7, 4, 4, 4, 5),
        (12, 2, 11, 11, 2),
        (6, 1, 6, 6, 1),
        (9, 5, 5, 2, 4),
        (4, 1, 2, 4, 3),
    )
    cases = tuple(
        _case(
            f'{size} {start_row} {start_column} {target_row} {target_column}\n',
            _knight_distance(size, start_row, start_column, target_row, target_column),
        )
        for size, start_row, start_column, target_row, target_column in raw_cases
    )
    return ProblemSpec(
        title="Knight's Shortest Escape",
        difficulty='hard',
        time_limit=2500,
        memory_limit=192,
        source='breadth-first search',
        description='Find the fewest knight moves between two cells on an empty square board.',
        input_description='The line contains board size n, start row and column, then target row and column; coordinates are 1-based.',
        output_description='Print the minimum number of moves, or -1 if the target is unreachable.',
        sample_input='5 1 1 4 4\n',
        sample_output='2\n',
        cases=cases,
    )


def _climb_spec():
    raw_cases = (
        [4, 7, 3, 8, 5],
        [1],
        [5, 5],
        [10, 1, 10, 1, 10],
        [0, 4, 4, 4],
        [9, 8, 7, 6, 5, 4],
        [3, 100, 2, 100, 1],
        [20, 1, 20, 1],
        [6, 2, 8, 3, 9, 1, 4],
        [100, 90, 80, 70, 60, 50],
    )
    cases = tuple(
        _case(f'{len(costs)}\n{_numbers(costs)}\n', _minimum_cost_climb(costs))
        for costs in raw_cases
    )
    return ProblemSpec(
        title='Minimum Cost Climb',
        difficulty='medium',
        time_limit=1500,
        memory_limit=128,
        source='dynamic programming',
        description='Reach the top by climbing one or two steps at a time while paying each entered step cost.',
        input_description='The first line contains n, followed by the nonnegative cost of each of n steps.',
        output_description='Print the minimum cost to enter the final step.',
        sample_input='5\n4 7 3 8 5\n',
        sample_output='12\n',
        cases=cases,
    )


def _edit_spec():
    raw_cases = (
        ('kitten', 'sitting'),
        ('a', 'a'),
        ('abc', 'xyz'),
        ('', 'abc'),
        ('algorithm', 'altruistic'),
        ('book', 'back'),
        ('aaaa', 'aa'),
        ('distance', 'instance'),
        ('spark', 'shark'),
        ('dynamic', 'program'),
    )
    cases = tuple(
        _case(f'{first}\n{second}\n', _edit_distance(first, second)) for first, second in raw_cases
    )
    return ProblemSpec(
        title='Edit Distance Lite',
        difficulty='hard',
        time_limit=2500,
        memory_limit=192,
        source='dynamic programming',
        description='Compute the minimum insertions, deletions, and substitutions to change one word into another.',
        input_description='Two lowercase words are given on separate lines; a word may be empty.',
        output_description='Print the minimum number of single-character edits.',
        sample_input='kitten\nsitting\n',
        sample_output='3\n',
        cases=cases,
    )


def get_specs() -> tuple[ProblemSpec, ...]:
    return (
        _first_beacon_spec(),
        _recharge_spec(),
        _range_increment_spec(),
        _largest_window_spec(),
        _treasure_spec(),
        _knight_spec(),
        _climb_spec(),
        _edit_spec(),
    )
