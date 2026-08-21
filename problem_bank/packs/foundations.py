from problem_bank.schema import ProblemSpec
from problem_bank.schema import TestCase


def _bill_after_discount(total, percent):
    return total * (100 - percent) // 100


def _days_in_month(year, month):
    if month == 2:
        is_leap_year = year % 400 == 0 or (year % 4 == 0 and year % 100 != 0)
        return 29 if is_leap_year else 28
    if month in {4, 6, 9, 11}:
        return 30
    return 31


def _sum_from_one_to_n(number):
    return number * (number + 1) // 2


def _count_numbers_with_seven(numbers):
    return sum('7' in str(abs(number)) for number in numbers)


def _temperature_zone(temperature):
    if temperature <= 0:
        return 'COLD'
    if temperature <= 25:
        return 'MILD'
    return 'HOT'


def _next_traffic_light(color, steps):
    colors = ('RED', 'GREEN', 'YELLOW')
    return colors[(colors.index(color) + steps) % len(colors)]


def _left_rotate(values, steps):
    offset = steps % len(values)
    return values[offset:] + values[:offset]


def _line(values):
    return ' '.join(str(value) for value in values)


def _make_bill_cases():
    raw_cases = (
        (0, 0),
        (1, 0),
        (100, 15),
        (999, 10),
        (50, 100),
        (75, 20),
        (1234, 5),
        (10000, 25),
        (7, 50),
        (99999, 1),
    )
    return tuple(
        TestCase(f'{total} {percent}\n', f'{_bill_after_discount(total, percent)}\n')
        for total, percent in raw_cases
    )


def _make_month_cases():
    raw_cases = (
        (2024, 2),
        (2023, 2),
        (1900, 2),
        (2000, 2),
        (2025, 1),
        (2025, 4),
        (2025, 6),
        (2025, 9),
        (2025, 11),
        (9999, 12),
    )
    return tuple(
        TestCase(f'{year} {month}\n', f'{_days_in_month(year, month)}\n')
        for year, month in raw_cases
    )


def _make_sum_cases():
    numbers = (0, 1, 2, 3, 10, 50, 100, 999, 10000, 100000)
    return tuple(TestCase(f'{number}\n', f'{_sum_from_one_to_n(number)}\n') for number in numbers)


def _make_seven_cases():
    raw_cases = (
        (1, (7,)),
        (5, (7, 17, 28, 70, 9)),
        (4, (1, 2, 3, 4)),
        (3, (-7, -17, -8)),
        (6, (70, 71, 72, 73, 74, 75)),
        (5, (0, -70, 6, 16, 27)),
        (2, (77, 88)),
        (7, (10, 20, 30, 40, 50, 60, 70)),
        (4, (107, 100, 700, 8)),
        (3, (999, 1000, 1234)),
    )
    return tuple(
        TestCase(f'{count}\n{_line(numbers)}\n', f'{_count_numbers_with_seven(numbers)}\n')
        for count, numbers in raw_cases
    )


def _make_temperature_cases():
    temperatures = (-100, -1, 0, 1, 10, 25, 26, 30, 100, 1000)
    return tuple(
        TestCase(f'{temperature}\n', f'{_temperature_zone(temperature)}\n')
        for temperature in temperatures
    )


def _make_traffic_cases():
    raw_cases = (
        ('RED', 0),
        ('RED', 1),
        ('RED', 2),
        ('RED', 3),
        ('RED', 4),
        ('GREEN', 1),
        ('YELLOW', 2),
        ('GREEN', 10),
        ('YELLOW', 100),
        ('RED', 1_000_000_000),
    )
    return tuple(
        TestCase(f'{color}\n{steps}\n', f'{_next_traffic_light(color, steps)}\n')
        for color, steps in raw_cases
    )


def _make_rotation_cases():
    raw_cases = (
        ((1,), 0),
        ((1,), 100),
        ((1, 2), 1),
        ((1, 2, 3, 4, 5), 2),
        ((1, 2, 3, 4, 5), 5),
        ((-1, -2, -3), 1),
        ((10, 20, 30, 40), 3),
        ((0, 0, 1, 0), 2),
        ((9, 8, 7, 6, 5, 4), 7),
        ((100,), 999999),
    )
    return tuple(
        TestCase(
            f'{len(values)} {steps}\n{_line(values)}\n',
            f'{_line(_left_rotate(values, steps))}\n',
        )
        for values, steps in raw_cases
    )


def get_specs() -> tuple[ProblemSpec, ...]:
    return (
        ProblemSpec(
            title='Bill After Discount',
            difficulty='easy',
            time_limit=1000,
            memory_limit=128,
            source='arithmetic',
            description=(
                'Given a non-negative bill total and a whole-number discount percentage, '
                'print the discounted total using integer arithmetic.'
            ),
            input_description='One line contains total and percent, where percent is from 0 to 100.',
            output_description='Print the discounted total.',
            sample_input='100 15\n',
            sample_output='85\n',
            cases=_make_bill_cases(),
        ),
        ProblemSpec(
            title='Days In Month',
            difficulty='easy',
            time_limit=1000,
            memory_limit=128,
            source='conditions',
            description='Given a year and month, print the number of days in that month.',
            input_description='One line contains a positive year and a month from 1 to 12.',
            output_description='Print 28, 29, 30, or 31.',
            sample_input='2024 2\n',
            sample_output='29\n',
            cases=_make_month_cases(),
        ),
        ProblemSpec(
            title='Sum From One To N',
            difficulty='easy',
            time_limit=1000,
            memory_limit=128,
            source='loops',
            description='Given a non-negative integer n, print the sum of all integers from 1 through n.',
            input_description='One line contains n, where 0 <= n <= 100000.',
            output_description='Print the requested sum.',
            sample_input='10\n',
            sample_output='55\n',
            cases=_make_sum_cases(),
        ),
        ProblemSpec(
            title='Count Numbers With Seven',
            difficulty='easy',
            time_limit=1000,
            memory_limit=128,
            source='loops and arrays',
            description='Count how many input numbers contain the digit 7 in their decimal notation.',
            input_description='The first line contains n. The second line contains n integers.',
            output_description='Print the count of numbers containing digit 7.',
            sample_input='5\n7 17 28 70 9\n',
            sample_output='3\n',
            cases=_make_seven_cases(),
        ),
        ProblemSpec(
            title='Temperature Zone',
            difficulty='easy',
            time_limit=1000,
            memory_limit=128,
            source='conditions',
            description='Classify a Celsius temperature as COLD, MILD, or HOT.',
            input_description='One line contains an integer temperature.',
            output_description='Print COLD for at most 0, MILD for 1 through 25, or HOT above 25.',
            sample_input='25\n',
            sample_output='MILD\n',
            cases=_make_temperature_cases(),
        ),
        ProblemSpec(
            title='Traffic Light After Steps',
            difficulty='easy',
            time_limit=1000,
            memory_limit=128,
            source='simulation',
            description='Advance a repeating RED, GREEN, YELLOW traffic light by a given number of steps.',
            input_description='The first line contains RED, GREEN, or YELLOW; the second contains steps.',
            output_description='Print the color after the steps, advancing one color per step.',
            sample_input='RED\n4\n',
            sample_output='GREEN\n',
            cases=_make_traffic_cases(),
        ),
        ProblemSpec(
            title='Left Rotate Array',
            difficulty='easy',
            time_limit=1000,
            memory_limit=128,
            source='basic arrays',
            description='Move the first k positions of an integer array to its end.',
            input_description='The first line contains n and k; the second line contains n integers.',
            output_description='Print the array after a left rotation by k positions.',
            sample_input='5 2\n1 2 3 4 5\n',
            sample_output='3 4 5 1 2\n',
            cases=_make_rotation_cases(),
        ),
    )
