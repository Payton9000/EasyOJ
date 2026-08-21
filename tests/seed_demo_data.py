import math
import os
from collections import deque
from datetime import datetime
from datetime import timedelta

from app import create_app
from app import db
from app.models import Contest
from app.models import ContestParticipant
from app.models import ContestProblem
from app.models import Problem
from app.models import User
from app.utils.file_utils import ensure_dir

ADMIN_SPEC = {
    'username': 'admin',
    'email': 'admin@easyoj.local',
    'role': 'admin',
    'password': 'admin123',
}

USER_SPECS = [
    {'username': 'alice', 'email': 'alice@easyoj.local', 'password': 'User@12345'},
    {'username': 'bob', 'email': 'bob@easyoj.local', 'password': 'User@12345'},
    {'username': 'carol', 'email': 'carol@easyoj.local', 'password': 'User@12345'},
    {'username': 'dave', 'email': 'dave@easyoj.local', 'password': 'User@12345'},
    {'username': 'eve', 'email': 'eve@easyoj.local', 'password': 'User@12345'},
    {'username': 'frank', 'email': 'frank@easyoj.local', 'password': 'User@12345'},
    {'username': 'grace', 'email': 'grace@easyoj.local', 'password': 'User@12345'},
    {'username': 'heidi', 'email': 'heidi@easyoj.local', 'password': 'User@12345'},
    {'username': 'ivan', 'email': 'ivan@easyoj.local', 'password': 'User@12345'},
    {'username': 'judy', 'email': 'judy@easyoj.local', 'password': 'User@12345'},
    {'username': 'mallory', 'email': 'mallory@easyoj.local', 'password': 'User@12345'},
    {'username': 'oscar', 'email': 'oscar@easyoj.local', 'password': 'User@12345'},
]


def _format_int_line(numbers):
    return ' '.join(str(x) for x in numbers)


def _knapsack_max_value(capacity, items):
    best = 0
    n = len(items)
    for mask in range(1 << n):
        total_w = 0
        total_v = 0
        for i in range(n):
            if (mask >> i) & 1:
                w, v = items[i]
                total_w += w
                total_v += v
        if total_w <= capacity and total_v > best:
            best = total_v
    return best


def _grid_shortest_distance(grid):
    rows = len(grid)
    cols = len(grid[0])
    start = None
    target = None
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == 'S':
                start = (r, c)
            elif grid[r][c] == 'T':
                target = (r, c)

    if start is None or target is None:
        return -1

    q = deque([(start[0], start[1], 0)])
    visited = {start}
    dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    while q:
        r, c, d = q.popleft()
        if (r, c) == target:
            return d
        for dr, dc in dirs:
            nr, nc = r + dr, c + dc
            if nr < 0 or nr >= rows or nc < 0 or nc >= cols:
                continue
            if grid[nr][nc] == '#':
                continue
            if (nr, nc) in visited:
                continue
            visited.add((nr, nc))
            q.append((nr, nc, d + 1))
    return -1


def _interval_max_count(intervals):
    sorted_intervals = sorted(intervals, key=lambda pair: (pair[1], pair[0]))
    count = 0
    last_end = -(10**18)
    for left, right in sorted_intervals:
        if left >= last_end:
            count += 1
            last_end = right
    return count


def _count_zero_indegree(n, edges):
    indegree = [0] * (n + 1)
    for _, v in edges:
        indegree[v] += 1
    return sum(1 for i in range(1, n + 1) if indegree[i] == 0)


def _is_balanced_brackets(s):
    pairs = {')': '(', ']': '[', '}': '{'}
    stack = []
    for ch in s:
        if ch in '([{':
            stack.append(ch)
        else:
            if not stack or stack[-1] != pairs.get(ch):
                return False
            stack.pop()
    return not stack


def _count_connected_components(n, edges):
    graph = [[] for _ in range(n + 1)]
    for u, v in edges:
        graph[u].append(v)
        graph[v].append(u)

    seen = [False] * (n + 1)
    comp = 0

    for node in range(1, n + 1):
        if seen[node]:
            continue
        comp += 1
        q = deque([node])
        seen[node] = True
        while q:
            cur = q.popleft()
            for nxt in graph[cur]:
                if not seen[nxt]:
                    seen[nxt] = True
                    q.append(nxt)
    return comp


def _lnds_length(arr):
    dp = [1] * len(arr)
    best = 0
    for i in range(len(arr)):
        for j in range(i):
            if arr[j] <= arr[i]:
                dp[i] = max(dp[i], dp[j] + 1)
        best = max(best, dp[i])
    return best


def _subarray_sum_equals_k_count(arr, k):
    count = 0
    prefix = 0
    freq = {0: 1}
    for x in arr:
        prefix += x
        count += freq.get(prefix - k, 0)
        freq[prefix] = freq.get(prefix, 0) + 1
    return count


def _matrix_border_sum(matrix):
    rows = len(matrix)
    cols = len(matrix[0])
    total = 0
    for r in range(rows):
        for c in range(cols):
            if r in (0, rows - 1) or c in (0, cols - 1):
                total += matrix[r][c]
    return total


def build_problem_specs():
    problem_specs = []

    ab_pairs = [
        (0, 0),
        (1, 2),
        (-5, 7),
        (999999999, 1),
        (-1000000000, -1000000000),
        (123456, -654321),
        (42, -42),
        (2147483647, -2147483648),
        (100000, 200000),
        (-999999, 123456),
    ]
    ab_cases = [(f'{a} {b}', str(a + b)) for a, b in ab_pairs]
    problem_specs.append(
        {
            'title': 'A+B Basic',
            'difficulty': 'easy',
            'time_limit': 1000,
            'memory_limit': 256,
            'source': 'math',
            'description': 'Given two integers A and B, output A+B.',
            'input_description': 'Two integers A and B.',
            'output_description': 'One integer, the sum.',
            'sample_input': '-2147483648 2147483647',
            'sample_output': '-1',
            'cases': ab_cases,
        }
    )

    triple_cases = [
        (3, 9, 4),
        (-1, -3, -2),
        (7, 7, 1),
        (100, 100, 100),
        (-10, 0, -5),
        (999999, 12345, 888888),
        (5, 4, 3),
        (-1000000, 1000000, 0),
        (42, 42, 41),
        (-7, -7, -8),
    ]
    max_three_cases = [(f'{a} {b} {c}', str(max(a, b, c))) for a, b, c in triple_cases]
    problem_specs.append(
        {
            'title': 'Max Of Three',
            'difficulty': 'easy',
            'time_limit': 1000,
            'memory_limit': 256,
            'source': 'implementation',
            'description': 'Given three integers, output the maximum.',
            'input_description': 'Three integers.',
            'output_description': 'Maximum value.',
            'sample_input': '-1000000 1000000 999999',
            'sample_output': '1000000',
            'cases': max_three_cases,
        }
    )

    words = [
        'a',
        'ab',
        'abba',
        'abcba',
        'abca',
        'aaaaabaaaaa',
        'xyzzyx',
        'xyzzx',
        'racecar',
        'easyoj',
    ]
    palindrome_cases = [(w, 'YES' if w == w[::-1] else 'NO') for w in words]
    problem_specs.append(
        {
            'title': 'Palindrome String',
            'difficulty': 'easy',
            'time_limit': 1000,
            'memory_limit': 256,
            'source': 'string',
            'description': 'Check whether a string is palindrome. Output YES or NO.',
            'input_description': 'One lowercase string without spaces.',
            'output_description': 'YES if palindrome else NO.',
            'sample_input': 'aaaaabaaaaa',
            'sample_output': 'YES',
            'cases': palindrome_cases,
        }
    )

    gcd_pairs = [
        (24, 18),
        (100, 75),
        (17, 13),
        (1, 999983),
        (270, 192),
        (123456, 7890),
        (99991, 97),
        (1000000000, 2),
        (999999937, 999999937),
        (84, 126),
    ]
    gcd_cases = [(f'{a} {b}', str(math.gcd(a, b))) for a, b in gcd_pairs]
    problem_specs.append(
        {
            'title': 'GCD Query',
            'difficulty': 'medium',
            'time_limit': 1000,
            'memory_limit': 256,
            'source': 'number theory',
            'description': 'Compute gcd(a, b).',
            'input_description': 'Two positive integers a and b.',
            'output_description': 'Greatest common divisor.',
            'sample_input': '123456 7890',
            'sample_output': str(math.gcd(123456, 7890)),
            'cases': gcd_cases,
        }
    )

    sum_arrays = [
        [1, 2, 3, 4, 5],
        [10, -2, 7],
        [42],
        [-1, -2, -3, -4, -5],
        [1000000, 1000000, -1000000],
        [0, 0, 0, 0],
        [9, 8, 7, 6, 5, 4],
        [3, -1, -2, 10, -10, 20],
        [999999999, 1],
        [5, -5, 5, -5, 5, -5, 5],
    ]
    range_sum_cases = []
    for arr in sum_arrays:
        range_sum_cases.append((f'{len(arr)}\n{_format_int_line(arr)}', str(sum(arr))))
    problem_specs.append(
        {
            'title': 'Range Sum 1D',
            'difficulty': 'medium',
            'time_limit': 1500,
            'memory_limit': 256,
            'source': 'prefix sum',
            'description': 'Given n and n integers, output the sum.',
            'input_description': 'First line n, second line n integers.',
            'output_description': 'One integer, total sum.',
            'sample_input': '7\n5 -5 5 -5 5 -5 5',
            'sample_output': '5',
            'cases': range_sum_cases,
        }
    )

    bs_raw = [
        ([1, 3, 7, 9, 11], 7),
        ([1, 2, 3, 4], 6),
        ([1, 2, 3, 4, 5, 6], 1),
        ([10, 20, 30, 40], 40),
        ([-5, -3, -1, 0, 2], -3),
        ([2, 4, 6, 8, 10, 12], 2),
        ([100], 100),
        ([100], -100),
        ([-10, -5, 0, 5, 10], 11),
        ([3, 6, 9, 12, 15, 18, 21], 15),
    ]
    bs_cases = []
    for arr, target in bs_raw:
        idx = arr.index(target) if target in arr else -1
        bs_cases.append((f'{len(arr)} {target}\n{_format_int_line(arr)}', str(idx)))
    problem_specs.append(
        {
            'title': 'Binary Search Position',
            'difficulty': 'medium',
            'time_limit': 1500,
            'memory_limit': 256,
            'source': 'binary search',
            'description': 'Given sorted array and target, output index (0-based), -1 if not found.',
            'input_description': 'n target in first line, sorted array in second line.',
            'output_description': 'Index or -1.',
            'sample_input': '5 -3\n-5 -3 -1 0 2',
            'sample_output': '1',
            'cases': bs_cases,
        }
    )

    knapsack_raw = [
        (5, [(2, 3), (3, 4), (4, 5)]),
        (7, [(6, 13), (4, 8), (3, 6), (5, 12)]),
        (10, [(3, 4), (4, 5)]),
        (9, [(2, 4), (2, 5), (6, 10), (5, 7)]),
        (8, [(1, 1), (3, 4), (4, 5), (5, 7)]),
        (15, [(12, 24), (7, 13), (11, 23), (8, 15), (9, 16)]),
        (6, [(4, 7), (2, 4), (3, 5)]),
        (20, [(5, 10), (10, 22), (12, 24), (6, 12), (7, 13)]),
        (13, [(3, 6), (5, 7), (6, 9), (7, 13)]),
        (4, [(5, 100), (4, 6), (3, 4)]),
    ]
    knapsack_cases = []
    for capacity, items in knapsack_raw:
        lines = [f'{len(items)} {capacity}']
        lines.extend(f'{w} {v}' for w, v in items)
        knapsack_cases.append(('\n'.join(lines), str(_knapsack_max_value(capacity, items))))
    problem_specs.append(
        {
            'title': 'Knapsack Tiny',
            'difficulty': 'hard',
            'time_limit': 2000,
            'memory_limit': 256,
            'source': 'dynamic programming',
            'description': '0-1 knapsack. Max value with capacity W.',
            'input_description': 'n W, then n lines weight value.',
            'output_description': 'Max achievable value.',
            'sample_input': '4 9\n2 4\n2 5\n6 10\n5 7',
            'sample_output': str(_knapsack_max_value(9, [(2, 4), (2, 5), (6, 10), (5, 7)])),
            'cases': knapsack_cases,
        }
    )

    grid_raw = [
        ['S..', '.#.', '..T'],
        ['S#', '#T'],
        ['ST'],
        ['S...', '.##.', '..#T'],
        ['S....', '####.', '....T'],
        ['S..#..', '.##.#.', '..#..T'],
        ['S#..', '.#.#', '.#T.', '....'],
        ['S....T'],
        ['S', '.', '.', 'T'],
        ['S#.#T', '.#.#.', '.#.#.', '.....'],
    ]
    bfs_cases = []
    for grid in grid_raw:
        rows = len(grid)
        cols = len(grid[0])
        bfs_cases.append((f'{rows} {cols}\n' + '\n'.join(grid), str(_grid_shortest_distance(grid))))
    problem_specs.append(
        {
            'title': 'Grid BFS Distance',
            'difficulty': 'hard',
            'time_limit': 2000,
            'memory_limit': 256,
            'source': 'graph bfs',
            'description': 'Shortest path from S to T in grid with 4 moves, walls are #.',
            'input_description': 'r c then r rows.',
            'output_description': 'Minimum steps or -1.',
            'sample_input': '3 4\nS...\n.##.\n..#T',
            'sample_output': str(_grid_shortest_distance(['S...', '.##.', '..#T'])),
            'cases': bfs_cases,
        }
    )

    interval_raw = [
        [(1, 2), (2, 3), (3, 4)],
        [(1, 5), (2, 3), (3, 4), (4, 6)],
        [(1, 10), (2, 9)],
        [(0, 1), (1, 1), (1, 2), (2, 2)],
        [(5, 7), (1, 2), (2, 5), (7, 9), (3, 4)],
        [(1, 4), (4, 8), (8, 12), (2, 3)],
        [(-5, -3), (-3, -1), (-2, 2), (2, 4)],
        [(10, 20), (0, 5), (5, 9), (9, 10), (20, 21)],
        [(1, 100), (10, 20), (20, 30), (30, 40), (40, 50)],
        [(3, 3), (3, 3), (3, 3), (3, 4)],
    ]
    interval_cases = []
    for intervals in interval_raw:
        lines = [str(len(intervals))]
        lines.extend(f'{left} {right}' for left, right in intervals)
        interval_cases.append(('\n'.join(lines), str(_interval_max_count(intervals))))
    problem_specs.append(
        {
            'title': 'Interval Scheduling',
            'difficulty': 'medium',
            'time_limit': 1500,
            'memory_limit': 256,
            'source': 'greedy',
            'description': 'Pick maximum number of non-overlapping intervals [l, r].',
            'input_description': 'n, then n lines l r.',
            'output_description': 'Maximum count.',
            'sample_input': '4\n0 1\n1 1\n1 2\n2 2',
            'sample_output': str(_interval_max_count([(0, 1), (1, 1), (1, 2), (2, 2)])),
            'cases': interval_cases,
        }
    )

    topo_raw = [
        (4, [(1, 2), (1, 3), (3, 4)]),
        (5, []),
        (3, [(1, 2), (2, 3)]),
        (6, [(1, 3), (2, 3), (4, 5)]),
        (4, [(1, 4), (2, 4), (3, 4)]),
        (7, [(1, 2), (2, 4), (3, 4), (5, 6)]),
        (2, [(1, 2)]),
        (8, [(1, 4), (2, 4), (3, 5), (6, 7), (7, 8)]),
        (5, [(2, 3), (4, 3), (1, 5)]),
        (6, [(1, 2), (1, 3), (4, 6)]),
    ]
    topo_cases = []
    for n, edges in topo_raw:
        lines = [f'{n} {len(edges)}']
        lines.extend(f'{u} {v}' for u, v in edges)
        topo_cases.append(('\n'.join(lines), str(_count_zero_indegree(n, edges))))
    problem_specs.append(
        {
            'title': 'Topological Sort Count Zero',
            'difficulty': 'hard',
            'time_limit': 2000,
            'memory_limit': 256,
            'source': 'dag',
            'description': 'Given DAG edges, output number of nodes with indegree zero.',
            'input_description': 'n m then m edges u v.',
            'output_description': 'Count of zero indegree nodes.',
            'sample_input': '6 3\n1 2\n1 3\n4 6',
            'sample_output': str(_count_zero_indegree(6, [(1, 2), (1, 3), (4, 6)])),
            'cases': topo_cases,
        }
    )

    bracket_inputs = [
        '()[]{}',
        '([{}])',
        '([)]',
        '(((())))',
        '([{}{}[]])',
        '([{}{}[]]))',
        '(((',
        '()()()()',
        '{[()]}[]',
        '{[(])}',
    ]
    bracket_cases = [(s, 'YES' if _is_balanced_brackets(s) else 'NO') for s in bracket_inputs]
    problem_specs.append(
        {
            'title': 'Bracket Sequence Validate',
            'difficulty': 'medium',
            'time_limit': 1000,
            'memory_limit': 256,
            'source': 'stack',
            'description': 'Given a bracket sequence of (), [], {}, determine whether it is balanced.',
            'input_description': 'One string containing only brackets.',
            'output_description': 'YES or NO.',
            'sample_input': '([{}{}[]]))',
            'sample_output': 'NO',
            'cases': bracket_cases,
        }
    )

    mod_pow_raw = [
        (2, 10, 1000),
        (3, 0, 5),
        (7, 13, 1000000007),
        (123456789, 123456, 1000003),
        (10, 9, 17),
        (99991, 99991, 998244353),
        (42, 42, 97),
        (5, 1234567, 19),
        (987654321, 2, 12345),
        (314159, 271828, 1009),
    ]
    mod_pow_cases = [(f'{a} {b} {m}', str(pow(a, b, m))) for a, b, m in mod_pow_raw]
    problem_specs.append(
        {
            'title': 'Modular Exponentiation',
            'difficulty': 'medium',
            'time_limit': 1000,
            'memory_limit': 256,
            'source': 'number theory',
            'description': 'Compute (a^b) mod m.',
            'input_description': 'Three integers a b m.',
            'output_description': 'One integer result.',
            'sample_input': '123456789 123456 1000003',
            'sample_output': str(pow(123456789, 123456, 1000003)),
            'cases': mod_pow_cases,
        }
    )

    component_raw = [
        (5, [(1, 2), (2, 3)]),
        (4, []),
        (6, [(1, 2), (2, 3), (4, 5), (5, 6)]),
        (7, [(1, 2), (2, 3), (3, 1), (4, 5)]),
        (3, [(1, 2), (2, 3)]),
        (8, [(1, 2), (3, 4), (5, 6), (7, 8)]),
        (6, [(1, 6), (2, 5), (3, 4)]),
        (5, [(1, 2), (2, 3), (3, 4), (4, 5)]),
        (9, [(1, 2), (2, 3), (4, 5), (6, 7), (7, 8)]),
        (10, [(1, 2), (2, 3), (3, 4), (8, 9)]),
    ]
    component_cases = []
    for n, edges in component_raw:
        lines = [f'{n} {len(edges)}']
        lines.extend(f'{u} {v}' for u, v in edges)
        component_cases.append(('\n'.join(lines), str(_count_connected_components(n, edges))))
    problem_specs.append(
        {
            'title': 'Connected Components Count',
            'difficulty': 'medium',
            'time_limit': 1500,
            'memory_limit': 256,
            'source': 'graph',
            'description': 'Given an undirected graph, output number of connected components.',
            'input_description': 'n m then m edges.',
            'output_description': 'Number of connected components.',
            'sample_input': '7 4\n1 2\n2 3\n3 1\n4 5',
            'sample_output': str(_count_connected_components(7, [(1, 2), (2, 3), (3, 1), (4, 5)])),
            'cases': component_cases,
        }
    )

    lnds_raw = [
        [1, 2, 3, 4],
        [4, 3, 2, 1],
        [5, 5, 5, 5],
        [1, 3, 2, 4, 3, 5],
        [10, 9, 2, 5, 3, 7, 101, 18],
        [2, 2, 1, 2, 2, 3],
        [9, 1, 8, 2, 7, 3, 6, 4, 5],
        [0, -1, -1, -1, 2],
        [3, 1, 2, 2, 2, 4],
        [7],
    ]
    lnds_cases = []
    for arr in lnds_raw:
        lnds_cases.append((f'{len(arr)}\n{_format_int_line(arr)}', str(_lnds_length(arr))))
    problem_specs.append(
        {
            'title': 'Longest Nondecreasing Subsequence',
            'difficulty': 'hard',
            'time_limit': 2000,
            'memory_limit': 256,
            'source': 'dynamic programming',
            'description': 'Given an array, output length of longest nondecreasing subsequence.',
            'input_description': 'n then n integers.',
            'output_description': 'One integer length.',
            'sample_input': '6\n3 1 2 2 2 4',
            'sample_output': str(_lnds_length([3, 1, 2, 2, 2, 4])),
            'cases': lnds_cases,
        }
    )

    subarray_raw = [
        ([1, 1, 1], 2),
        ([1, 2, 3], 3),
        ([0, 0, 0], 0),
        ([3, 4, -7, 1, 3, 3, 1, -4], 7),
        ([1, -1, 1, -1, 1], 0),
        ([5, -2, -3, 1, 2], 3),
        ([2, 2, 2, 2], 4),
        ([-1, -1, 1], 0),
        ([10, -10, 10, -10], 0),
        ([1, 3, -2, 5, -3, 2], 4),
    ]
    subarray_cases = []
    for arr, k in subarray_raw:
        subarray_cases.append(
            (f'{len(arr)} {k}\n{_format_int_line(arr)}', str(_subarray_sum_equals_k_count(arr, k)))
        )
    problem_specs.append(
        {
            'title': 'Subarray Sum Equals K Count',
            'difficulty': 'hard',
            'time_limit': 2000,
            'memory_limit': 256,
            'source': 'prefix sum + hash',
            'description': 'Count subarrays whose sum equals k.',
            'input_description': 'n k in first line, n integers in second line.',
            'output_description': 'Count of valid subarrays.',
            'sample_input': '8 7\n3 4 -7 1 3 3 1 -4',
            'sample_output': str(_subarray_sum_equals_k_count([3, 4, -7, 1, 3, 3, 1, -4], 7)),
            'cases': subarray_cases,
        }
    )

    matrix_raw = [
        [[1, 2], [3, 4]],
        [[5]],
        [[1, 2, 3, 4]],
        [[1], [2], [3], [4]],
        [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
        [[-1, -2, -3], [-4, 100, -6], [-7, -8, -9]],
        [[10, 20, 30, 40], [50, 60, 70, 80], [90, 100, 110, 120]],
        [[0, 0, 0], [0, 0, 0]],
        [[7, 8, 9], [1, 2, 3]],
        [[3, 1, 4, 1, 5], [9, 2, 6, 5, 3], [5, 8, 9, 7, 9], [3, 2, 3, 8, 4]],
    ]
    matrix_cases = []
    for matrix in matrix_raw:
        r = len(matrix)
        c = len(matrix[0])
        lines = [f'{r} {c}']
        lines.extend(_format_int_line(row) for row in matrix)
        matrix_cases.append(('\n'.join(lines), str(_matrix_border_sum(matrix))))
    problem_specs.append(
        {
            'title': 'Matrix Border Sum',
            'difficulty': 'medium',
            'time_limit': 1500,
            'memory_limit': 256,
            'source': 'matrix',
            'description': 'Given a matrix, output the sum of all border elements.',
            'input_description': 'r c then matrix values.',
            'output_description': 'Border sum.',
            'sample_input': '3 3\n1 2 3\n4 5 6\n7 8 9',
            'sample_output': str(_matrix_border_sum([[1, 2, 3], [4, 5, 6], [7, 8, 9]])),
            'cases': matrix_cases,
        }
    )

    return problem_specs


PROBLEM_SPECS = build_problem_specs()

CONTEST_SPECS = [
    {
        'title': 'Spring Weekly Contest Alpha',
        'description': 'Mixed beginner and intermediate tasks.',
        'start_offset_days': -1,
        'problem_titles': [
            'A+B Basic',
            'Palindrome String',
            'Range Sum 1D',
            'Binary Search Position',
        ],
        'participant_usernames': ['alice', 'bob', 'carol', 'dave', 'eve', 'frank'],
    },
    {
        'title': 'Spring Weekly Contest Beta',
        'description': 'Greedy, graph and DP themed contest.',
        'start_offset_days': 2,
        'problem_titles': [
            'Interval Scheduling',
            'Grid BFS Distance',
            'Knapsack Tiny',
            'Topological Sort Count Zero',
        ],
        'participant_usernames': ['grace', 'heidi', 'ivan', 'judy', 'mallory', 'oscar'],
    },
    {
        'title': 'Spring Weekly Contest Gamma',
        'description': 'Comprehensive mixed challenge.',
        'start_offset_days': -14,
        'problem_titles': [
            'A+B Basic',
            'GCD Query',
            'Max Of Three',
            'Grid BFS Distance',
            'Topological Sort Count Zero',
        ],
        'participant_usernames': ['alice', 'carol', 'grace', 'judy', 'oscar'],
    },
]


def upsert_user(username, email, role, password):
    user = User.query.filter_by(username=username).first()
    created = False
    if user is None:
        user = User(username=username)
        created = True
    user.email = email
    user.role = role
    user.is_active = True
    user.set_password(password)
    if created:
        db.session.add(user)
    return user, created


def write_problem_testcases(base_dir, problem_id, cases):
    testcase_dir = os.path.join(base_dir, 'data', 'problems', str(problem_id), 'testcases')
    ensure_dir(testcase_dir)

    # Keep testcase files aligned with current seed spec.
    for name in os.listdir(testcase_dir):
        if name.endswith('.in') or name.endswith('.out'):
            os.remove(os.path.join(testcase_dir, name))

    for index, (input_data, expected_output) in enumerate(cases, 1):
        in_path = os.path.join(testcase_dir, f'{index}.in')
        out_path = os.path.join(testcase_dir, f'{index}.out')
        with open(in_path, 'w', encoding='utf-8') as f_in:
            f_in.write(input_data.rstrip('\n') + '\n')
        with open(out_path, 'w', encoding='utf-8') as f_out:
            f_out.write(expected_output.rstrip('\n') + '\n')


def upsert_problem(spec, admin_id, base_dir):
    if len(spec['cases']) < 10:
        raise ValueError(f"Problem '{spec['title']}' must contain at least 10 test cases")

    problem = Problem.query.filter_by(title=spec['title']).first()
    created = False
    if problem is None:
        problem = Problem(title=spec['title'])
        created = True

    problem.description = spec['description']
    problem.input_description = spec['input_description']
    problem.output_description = spec['output_description']
    problem.sample_input = spec['sample_input']
    problem.sample_output = spec['sample_output']
    problem.time_limit = spec['time_limit']
    problem.memory_limit = spec['memory_limit']
    problem.difficulty = spec['difficulty']
    problem.source = spec['source']
    problem.is_public = True
    problem.created_by = admin_id

    if created:
        db.session.add(problem)

    db.session.flush()
    write_problem_testcases(base_dir, problem.id, spec['cases'])
    return problem, created


def sync_contest_problems(contest, problem_title_to_id, titles):
    desired_pairs = []
    for index, title in enumerate(titles, 1):
        desired_pairs.append((problem_title_to_id[title], index, chr(ord('A') + index - 1)))

    existing = ContestProblem.query.filter_by(contest_id=contest.id).all()
    existing_by_pid = {row.problem_id: row for row in existing}
    desired_problem_ids = {pid for pid, _, _ in desired_pairs}

    for row in existing:
        if row.problem_id not in desired_problem_ids:
            db.session.delete(row)

    for pid, display_order, alias in desired_pairs:
        row = existing_by_pid.get(pid)
        if row is None:
            row = ContestProblem(contest_id=contest.id, problem_id=pid)
            db.session.add(row)
        row.display_order = display_order
        row.alias = alias


def sync_contest_participants(contest, username_to_id, usernames):
    desired_ids = {username_to_id[name] for name in usernames}
    existing = ContestParticipant.query.filter_by(contest_id=contest.id).all()
    existing_by_uid = {row.user_id: row for row in existing}

    for row in existing:
        if row.user_id not in desired_ids:
            db.session.delete(row)

    for uid in desired_ids:
        row = existing_by_uid.get(uid)
        if row is None:
            row = ContestParticipant(contest_id=contest.id, user_id=uid)
            db.session.add(row)
        row.is_disqualified = False


def upsert_contest(spec, admin_id, problem_title_to_id, username_to_id, now_utc):
    contest = Contest.query.filter_by(title=spec['title']).first()
    created = False
    if contest is None:
        contest = Contest(title=spec['title'])
        created = True

    start_time = now_utc + timedelta(days=spec['start_offset_days'])
    end_time = start_time + timedelta(days=7)

    contest.description = spec['description']
    contest.start_time = start_time
    contest.end_time = end_time
    contest.is_public = True
    contest.is_sealed = False
    contest.password = None
    contest.max_participants = 0
    contest.created_by = admin_id

    if created:
        db.session.add(contest)

    db.session.flush()
    sync_contest_problems(contest, problem_title_to_id, spec['problem_titles'])
    sync_contest_participants(contest, username_to_id, spec['participant_usernames'])
    return contest, created


def seed_demo_data():
    app = create_app('development', start_judge_engine=False)

    with app.app_context():
        db.create_all()

        created_users = 0
        created_problems = 0
        created_contests = 0

        admin, admin_created = upsert_user(
            ADMIN_SPEC['username'],
            ADMIN_SPEC['email'],
            ADMIN_SPEC['role'],
            ADMIN_SPEC['password'],
        )
        created_users += 1 if admin_created else 0

        normal_users = []
        for user_spec in USER_SPECS:
            user, created = upsert_user(
                user_spec['username'],
                user_spec['email'],
                'user',
                user_spec['password'],
            )
            normal_users.append(user)
            created_users += 1 if created else 0

        db.session.commit()

        base_dir = os.path.abspath(os.path.join(app.root_path, '..'))
        admin_id = admin.id

        problem_title_to_id = {}
        for problem_spec in PROBLEM_SPECS:
            problem, created = upsert_problem(problem_spec, admin_id, base_dir)
            problem_title_to_id[problem_spec['title']] = problem.id
            created_problems += 1 if created else 0

        db.session.commit()

        username_to_id = {u.username: u.id for u in normal_users}
        now_utc = datetime.utcnow().replace(microsecond=0)

        for contest_spec in CONTEST_SPECS:
            contest, created = upsert_contest(
                contest_spec,
                admin_id,
                problem_title_to_id,
                username_to_id,
                now_utc,
            )
            created_contests += 1 if created else 0

        db.session.commit()

        print('Seed completed successfully.')
        print(f'Users total: {User.query.count()} (newly created: {created_users})')
        print(f'Problems total: {Problem.query.count()} (newly created: {created_problems})')
        print(f'Contests total: {Contest.query.count()} (newly created: {created_contests})')
        print('Admin account: admin / admin123')
        print('User accounts:')
        for user_spec in USER_SPECS:
            print(f"  - {user_spec['username']} / {user_spec['password']}")


if __name__ == '__main__':
    seed_demo_data()
