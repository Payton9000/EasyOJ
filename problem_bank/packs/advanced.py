from bisect import bisect_right
from collections import deque
from functools import cache

from problem_bank.schema import ProblemSpec
from problem_bank.schema import TestCase

MODULUS = 1_000_000_007


def _numbers(values):
    return ' '.join(str(value) for value in values)


def _case(input_data, expected_output):
    if not expected_output.endswith('\n'):
        expected_output += '\n'
    return TestCase(input_data=input_data, expected_output=expected_output)


def _bridge_count(node_count, edges):
    graph = [[] for _ in range(node_count)]
    for edge_id, (left, right) in enumerate(edges):
        left -= 1
        right -= 1
        graph[left].append((right, edge_id))
        graph[right].append((left, edge_id))

    discovery = [-1] * node_count
    low = [0] * node_count
    time = 0
    bridges = 0

    def visit(node, parent_edge):
        nonlocal bridges, time
        discovery[node] = low[node] = time
        time += 1
        for neighbor, edge_id in graph[node]:
            if edge_id == parent_edge:
                continue
            if discovery[neighbor] == -1:
                visit(neighbor, edge_id)
                low[node] = min(low[node], low[neighbor])
                bridges += low[neighbor] > discovery[node]
            else:
                low[node] = min(low[node], discovery[neighbor])

    for node in range(node_count):
        if discovery[node] == -1:
            visit(node, -1)
    return bridges


def _bridge_spec():
    raw_cases = (
        (5, ((1, 2), (2, 3), (3, 1), (3, 4), (4, 5))),
        (2, ((1, 2),)),
        (3, ((1, 2), (2, 3))),
        (4, ((1, 2), (2, 3), (3, 4), (4, 1))),
        (2, ((1, 2), (1, 2))),
        (5, ((1, 2), (2, 3), (3, 1), (4, 5))),
        (6, ((1, 2), (2, 3), (3, 4), (4, 5), (5, 6))),
        (6, ((1, 2), (2, 3), (3, 1), (4, 5), (5, 6), (6, 4), (3, 4))),
        (7, ((1, 2), (2, 3), (3, 1), (3, 4), (4, 5), (5, 6), (6, 7), (7, 5))),
        (4, ()),
    )
    cases = []
    for node_count, edges in raw_cases:
        lines = [f'{node_count} {len(edges)}']
        lines.extend(f'{left} {right}' for left, right in edges)
        cases.append(_case('\n'.join(lines) + '\n', str(_bridge_count(node_count, edges))))
    return ProblemSpec(
        title='Critical Road Bridges',
        difficulty='hard',
        time_limit=2500,
        memory_limit=192,
        source='Tarjan low-link graph traversal',
        description='Count the roads whose removal disconnects an undirected road network.',
        input_description=(
            'The first line contains n and m (1 <= n <= 20000, 0 <= m <= 40000), '
            'followed by m undirected edges with 1-based endpoints.'
        ),
        output_description='Print the number of bridges in the network.',
        sample_input='5 5\n1 2\n2 3\n3 1\n3 4\n4 5\n',
        sample_output='2\n',
        cases=tuple(cases),
    )


def _tree_distance_totals(node_count, edges):
    graph = [[] for _ in range(node_count)]
    for left, right in edges:
        left -= 1
        right -= 1
        graph[left].append(right)
        graph[right].append(left)

    parent = [-1] * node_count
    order = [0]
    for node in order:
        for neighbor in graph[node]:
            if neighbor != parent[node]:
                parent[neighbor] = node
                order.append(neighbor)

    subtree_size = [1] * node_count
    for node in reversed(order[1:]):
        subtree_size[parent[node]] += subtree_size[node]

    root_total = sum(depth for depth in range(node_count))
    if node_count > 1:
        root_total = 0
        queue = deque([(0, 0)])
        while queue:
            node, depth = queue.popleft()
            root_total += depth
            queue.extend(
                (neighbor, depth + 1) for neighbor in graph[node] if neighbor != parent[node]
            )

    totals = [0] * node_count
    totals[0] = root_total
    for node in order[1:]:
        totals[node] = totals[parent[node]] + node_count - 2 * subtree_size[node]
    return totals


def _tree_distance_spec():
    raw_cases = (
        (1, ()),
        (2, ((1, 2),)),
        (3, ((1, 2), (2, 3))),
        (4, ((1, 2), (2, 3), (3, 4))),
        (4, ((1, 2), (1, 3), (1, 4))),
        (5, ((1, 2), (2, 3), (2, 4), (4, 5))),
        (6, ((1, 2), (1, 3), (2, 4), (2, 5), (3, 6))),
        (7, ((1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7))),
        (8, ((1, 2), (1, 3), (2, 4), (2, 5), (3, 6), (3, 7), (7, 8))),
        (10, ((1, 2), (2, 3), (2, 4), (4, 5), (4, 6), (3, 7), (7, 8), (7, 9), (9, 10))),
    )
    cases = []
    for node_count, edges in raw_cases:
        lines = [str(node_count)]
        lines.extend(f'{left} {right}' for left, right in edges)
        cases.append(
            _case('\n'.join(lines) + '\n', _numbers(_tree_distance_totals(node_count, edges)))
        )
    return ProblemSpec(
        title='Rerooted Tree Distance Totals',
        difficulty='hard',
        time_limit=2500,
        memory_limit=192,
        source='tree rerooting and subtree sizes',
        description='For every tree vertex, compute the sum of its distances to all other vertices.',
        input_description=(
            'The first line contains n (1 <= n <= 20000), followed by n-1 edges of a connected tree.'
        ),
        output_description='Print n distance totals in vertex order on one line.',
        sample_input='4\n1 2\n2 3\n3 4\n',
        sample_output='6 4 4 6\n',
        cases=tuple(cases),
    )


def _weighted_revenue(intervals):
    ordered = sorted(intervals, key=lambda interval: interval[1])
    ends = [interval[1] for interval in ordered]
    best = [0]
    for start, _, value in ordered:
        previous = bisect_right(ends, start)
        best.append(max(best[-1], best[previous] + value))
    return best[-1]


def _weighted_spec():
    raw_cases = (
        ((1, 3, 5), (2, 5, 6), (3, 6, 5), (6, 8, 7)),
        (),
        ((1, 2, 10),),
        ((1, 4, 5), (4, 6, 7)),
        ((1, 3, 4), (2, 5, 10), (5, 7, 8)),
        ((0, 2, -3), (2, 4, 5), (4, 5, 2)),
        ((1, 10, 50), (2, 3, 9), (3, 5, 9), (5, 7, 9), (7, 9, 9)),
        ((1, 2, 4), (1, 2, 7), (2, 3, 2), (2, 4, 10)),
        ((3, 4, 6), (1, 3, 5), (4, 8, 9), (8, 9, 1)),
        ((-2, 0, 3), (0, 2, 4), (2, 5, 8), (-1, 5, 20)),
    )
    cases = []
    for intervals in raw_cases:
        lines = [str(len(intervals))]
        lines.extend(f'{start} {end} {value}' for start, end, value in intervals)
        cases.append(_case('\n'.join(lines) + '\n', str(_weighted_revenue(intervals))))
    return ProblemSpec(
        title='Weighted Interval Revenue',
        difficulty='hard',
        time_limit=2000,
        memory_limit=160,
        source='weighted interval dynamic programming',
        description='Choose non-overlapping jobs to maximize total revenue, allowing a job to start when another ends.',
        input_description=(
            'The first line contains n (0 <= n <= 20000), followed by n lines of start time, '
            'end time, and revenue.'
        ),
        output_description='Print the maximum revenue obtainable from compatible jobs.',
        sample_input='4\n1 3 5\n2 5 6\n3 6 5\n6 8 7\n',
        sample_output='17\n',
        cases=tuple(cases),
    )


def _minimum_palindrome_cuts(word):
    length = len(word)
    if not word:
        return 0
    palindrome = [[False] * length for _ in range(length)]
    cuts = [length] * (length + 1)
    cuts[0] = -1
    for right in range(length):
        for left in range(right + 1):
            if word[left] == word[right] and (right - left < 2 or palindrome[left + 1][right - 1]):
                palindrome[left][right] = True
                cuts[right + 1] = min(cuts[right + 1], cuts[left] + 1)
    return cuts[length]


def _palindrome_spec():
    words = (
        'aabcb',
        'a',
        'abba',
        'abc',
        'aab',
        'racecarxyz',
        'banana',
        'noonabbad',
        'aaaaab',
        'abcbaefg',
    )
    cases = tuple(_case(f'{word}\n', str(_minimum_palindrome_cuts(word))) for word in words)
    return ProblemSpec(
        title='Minimum Palindrome Cuts',
        difficulty='hard',
        time_limit=2200,
        memory_limit=192,
        source='palindrome interval dynamic programming',
        description='Split a lowercase string into palindromic pieces using as few cuts as possible.',
        input_description='One line contains a lowercase string of length at most 500.',
        output_description='Print the minimum number of cuts needed; the empty string needs zero cuts.',
        sample_input='aabcb\n',
        sample_output='1\n',
        cases=cases,
    )


def _range_minimum(values, operations):
    answers = []
    values = list(values)
    for operation in operations:
        if operation[0] == 'U':
            values[operation[1] - 1] = operation[2]
        else:
            left, right = operation[1:]
            answers.append(min(values[left - 1 : right]))
    return answers


def _range_minimum_spec():
    raw_cases = (
        ((5, 2, 7, 1, 6), (('Q', 1, 5), ('Q', 2, 3), ('U', 4, -3), ('Q', 3, 5))),
        ((4,), (('Q', 1, 1),)),
        ((5, 5, 5), (('U', 2, -1), ('Q', 1, 3), ('Q', 2, 2))),
        ((-2, 8, 0, 4), (('Q', 2, 4), ('U', 1, 9), ('Q', 1, 2))),
        ((9, 1, 8, 2, 7, 3), (('Q', 1, 6), ('U', 3, -5), ('Q', 2, 4), ('U', 6, -6))),
        ((0, 0, 0, 0), (('U', 4, 12), ('Q', 1, 4), ('Q', 4, 4))),
        ((10, -4, 6, 3, -8), (('Q', 1, 2), ('Q', 3, 5), ('U', 2, 11), ('Q', 1, 3))),
        ((100, 90), (('U', 1, -100), ('Q', 1, 2))),
        ((7, 6, 5, 4, 3, 2, 1), (('Q', 2, 6), ('U', 7, 20), ('Q', 1, 7))),
        ((-10, 10, -5, 5), (('Q', 1, 4), ('U', 2, -20), ('Q', 1, 2))),
    )
    cases = []
    for values, operations in raw_cases:
        lines = [f'{len(values)} {len(operations)}', _numbers(values)]
        lines.extend(' '.join(map(str, operation)) for operation in operations)
        output = '\n'.join(map(str, _range_minimum(values, operations)))
        cases.append(_case('\n'.join(lines) + '\n', output))
    return ProblemSpec(
        title='Dynamic Range Minimum',
        difficulty='hard',
        time_limit=2200,
        memory_limit=192,
        source='segment tree point updates and range queries',
        description='Maintain an integer array while answering inclusive range-minimum queries after point updates.',
        input_description=(
            'The first line contains n and q (1 <= n <= 20000, 1 <= q <= 40000), followed '
            'by n values and q operations Q l r or U i value.'
        ),
        output_description='Print the result of each Q operation on its own line.',
        sample_input='5 4\n5 2 7 1 6\nQ 1 5\nQ 2 3\nU 4 -3\nQ 3 5\n',
        sample_output='1\n2\n-3\n',
        cases=tuple(cases),
    )


def _sliding_median_total(values, width):
    return sum(
        sorted(values[index : index + width])[(width - 1) // 2]
        for index in range(len(values) - width + 1)
    )


def _sliding_median_spec():
    raw_cases = (
        (6, 3, (2, 1, 5, 7, 2, 3)),
        (1, 1, (9,)),
        (5, 2, (-5, -2, -7, -1, -3)),
        (5, 5, (4, 1, 9, 2, 7)),
        (7, 3, (10, -5, 4, -2, 8, -1, 3)),
        (8, 4, (0, 0, 1, 0, 2, 2, -1, 3)),
        (6, 2, (100, -100, 50, -50, 25, -25)),
        (9, 5, (3, 8, 2, 9, 1, 7, 4, 6, 5)),
        (10, 1, (-4, 2, 0, 7, -3, 5, -9, 8, 1, 6)),
        (7, 6, (5, 5, 5, 4, 4, 4, 3)),
    )
    cases = tuple(
        _case(f'{length} {width}\n{_numbers(values)}\n', str(_sliding_median_total(values, width)))
        for length, width, values in raw_cases
    )
    return ProblemSpec(
        title='Sliding Median Total',
        difficulty='hard',
        time_limit=2200,
        memory_limit=192,
        source='two-heaps sliding-window data structure',
        description='Sum the lower median of every fixed-width sliding window in an integer sequence.',
        input_description=(
            'The first line contains n and k (1 <= k <= n <= 20000), followed by n integers.'
        ),
        output_description='For each window use the lower middle value when k is even, then print the sum of medians.',
        sample_input='6 3\n2 1 5 7 2 3\n',
        sample_output='15\n',
        cases=cases,
    )


def _grouping_count(item_count, group_count):
    table = [[0] * (group_count + 1) for _ in range(item_count + 1)]
    table[0][0] = 1
    for item in range(1, item_count + 1):
        for groups in range(1, min(item, group_count) + 1):
            table[item][groups] = (
                table[item - 1][groups - 1] + groups * table[item - 1][groups]
            ) % MODULUS
    return table[item_count][group_count]


def _grouping_spec():
    raw_cases = ((5, 2), (1, 1), (2, 1), (2, 2), (3, 2), (4, 2), (4, 3), (6, 3), (8, 4), (12, 5))
    cases = tuple(
        _case(f'{item_count} {group_count}\n', str(_grouping_count(item_count, group_count)))
        for item_count, group_count in raw_cases
    )
    return ProblemSpec(
        title='Exact Nonempty Groupings',
        difficulty='hard',
        time_limit=1800,
        memory_limit=160,
        source='Stirling-number combinatorial dynamic programming',
        description='Count the ways to split n distinct students into exactly k unlabeled nonempty groups.',
        input_description='One line contains n and k, with 0 <= k <= n <= 200.',
        output_description='Print the count modulo 1000000007.',
        sample_input='5 2\n',
        sample_output='15\n',
        cases=cases,
    )


def _kth_parentheses(pair_count, rank):
    @cache
    def completions(opened, closed):
        if opened == pair_count and closed == pair_count:
            return 1
        total = 0
        if opened < pair_count:
            total += completions(opened + 1, closed)
        if closed < opened:
            total += completions(opened, closed + 1)
        return total

    if rank < 1 or rank > completions(0, 0):
        return 'NONE'
    opened = closed = 0
    result = []
    while opened < pair_count or closed < pair_count:
        if opened < pair_count:
            opening_count = completions(opened + 1, closed)
            if rank <= opening_count:
                result.append('(')
                opened += 1
                continue
            rank -= opening_count
        if closed == opened:
            return 'NONE'
        result.append(')')
        closed += 1
    return ''.join(result)


def _parentheses_spec():
    raw_cases = ((3, 4), (1, 1), (2, 1), (2, 2), (3, 1), (3, 5), (3, 6), (4, 7), (4, 14), (8, 100))
    cases = tuple(
        _case(f'{pair_count} {rank}\n', _kth_parentheses(pair_count, rank))
        for pair_count, rank in raw_cases
    )
    return ProblemSpec(
        title='Kth Balanced Parentheses',
        difficulty='hard',
        time_limit=1800,
        memory_limit=160,
        source='Catalan counting and combinatorial unranking',
        description='Construct the rank-th balanced-parentheses string in lexicographic order.',
        input_description=(
            'One line contains n and k (1 <= n <= 1000, 1 <= k <= 10^18), where n is the '
            'number of pairs and k is 1-based.'
        ),
        output_description='Print the k-th string, or NONE when k exceeds the Catalan count.',
        sample_input='3 4\n',
        sample_output='()(())\n',
        cases=cases,
    )


def get_specs() -> tuple[ProblemSpec, ...]:
    return (
        _bridge_spec(),
        _tree_distance_spec(),
        _weighted_spec(),
        _palindrome_spec(),
        _range_minimum_spec(),
        _sliding_median_spec(),
        _grouping_spec(),
        _parentheses_spec(),
    )
