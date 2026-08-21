import pytest

from problem_bank.schema import ProblemSpec
from problem_bank.schema import TestCase as ProblemTestCase
from problem_bank.validation import validate_catalog


def _spec(**overrides):
    values = {
        'title': 'Fresh Problem',
        'difficulty': 'easy',
        'time_limit': 1000,
        'memory_limit': 128,
        'source': 'fundamentals',
        'description': 'Solve the stated task.',
        'input_description': 'Read the input.',
        'output_description': 'Print the answer.',
        'sample_input': '1\n',
        'sample_output': '1\n',
        'cases': tuple(ProblemTestCase(f'{index}\n', f'{index}\n') for index in range(10)),
    }
    values.update(overrides)
    return ProblemSpec(**values)


def test_validate_catalog_accepts_a_well_formed_problem():
    validate_catalog((_spec(),))


@pytest.mark.parametrize(
    ('overrides', 'message'),
    [
        ({'difficulty': 'expert'}, 'difficulty'),
        ({'cases': tuple()}, 'at least 10'),
        ({'sample_input': '2\\n1 2'}, 'literal'),
        (
            {'cases': tuple([ProblemTestCase('2\\n1 2', '3')] * 10)},
            'literal',
        ),
        ({'sample_output': 'x' * (256 * 1024 + 1)}, '256 KiB'),
    ],
)
def test_validate_catalog_rejects_malformed_problem(overrides, message):
    with pytest.raises(ValueError, match=message):
        validate_catalog((_spec(**overrides),))


def test_validate_catalog_rejects_duplicate_titles_case_insensitively():
    with pytest.raises(ValueError, match='Duplicate problem title'):
        validate_catalog((_spec(title='Unique Name'), _spec(title=' unique name ')))
