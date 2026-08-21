from collections.abc import Sequence

from problem_bank.schema import ProblemSpec

_ALLOWED_DIFFICULTIES = frozenset({'easy', 'medium', 'hard'})
_MAX_TEXT_BYTES = 256 * 1024
_LITERAL_NEWLINE_ESCAPE = chr(92) + 'n'


def _validate_text(problem_title, field_name, value):
    if not isinstance(value, str):
        raise ValueError(f'{problem_title}: {field_name} must be text')
    if _LITERAL_NEWLINE_ESCAPE in value:
        raise ValueError(f'{problem_title}: {field_name} contains a literal newline escape')
    if len(value.encode('utf-8')) > _MAX_TEXT_BYTES:
        raise ValueError(f'{problem_title}: {field_name} exceeds 256 KiB')


def _validate_problem(spec):
    title = spec.title.strip()
    if not title:
        raise ValueError('Problem title must not be empty')
    if spec.difficulty not in _ALLOWED_DIFFICULTIES:
        raise ValueError(f'{title}: invalid difficulty')
    if not isinstance(spec.time_limit, int) or not 1 <= spec.time_limit <= 20000:
        raise ValueError(f'{title}: time_limit must be between 1 and 20000 ms')
    if not isinstance(spec.memory_limit, int) or not 1 <= spec.memory_limit <= 512:
        raise ValueError(f'{title}: memory_limit must be between 1 and 512 MB')
    if len(spec.cases) < 10:
        raise ValueError(f'{title}: at least 10 test cases are required')

    for field_name in (
        'source',
        'description',
        'input_description',
        'output_description',
        'sample_input',
        'sample_output',
    ):
        _validate_text(title, field_name, getattr(spec, field_name))

    for index, case in enumerate(spec.cases, 1):
        _validate_text(title, f'case {index} input', case.input_data)
        _validate_text(title, f'case {index} output', case.expected_output)


def validate_catalog(specs: Sequence[ProblemSpec]) -> None:
    seen_titles = set()
    for spec in specs:
        if not isinstance(spec, ProblemSpec):
            raise ValueError('Catalog entries must be ProblemSpec instances')
        normalized_title = spec.title.strip().casefold()
        if normalized_title in seen_titles:
            raise ValueError(f'Duplicate problem title: {spec.title.strip()}')
        seen_titles.add(normalized_title)
        _validate_problem(spec)
