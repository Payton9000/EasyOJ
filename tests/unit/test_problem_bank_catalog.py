from problem_bank.catalog import get_specs
from problem_bank.validation import validate_catalog


def test_builtin_catalog_contains_thirty_unique_validated_specs():
    specs = get_specs()

    validate_catalog(specs)
    assert len(specs) == 30
    assert {spec.difficulty for spec in specs} == {'easy', 'medium', 'hard'}
    assert len({spec.title.casefold() for spec in specs}) == 30
    assert all(len(spec.cases) >= 10 for spec in specs)
    assert all('\n' in spec.sample_input and '\n' in spec.sample_output for spec in specs)
