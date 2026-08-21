from problem_bank.catalog import get_specs


def test_builtin_catalog_contains_thirty_unique_validated_specs():
    specs = get_specs()

    assert len(specs) == 30
    assert {spec.difficulty for spec in specs} == {'easy', 'medium', 'hard'}
    assert len({spec.title.casefold() for spec in specs}) == 30
    assert all(len(spec.cases) >= 10 for spec in specs)


def test_builtin_catalog_has_no_literal_newline_escapes():
    literal_escape = chr(92) + 'n'

    for spec in get_specs():
        texts = (
            spec.sample_input,
            spec.sample_output,
            *(case.input_data for case in spec.cases),
            *(case.expected_output for case in spec.cases),
        )
        assert all(literal_escape not in text for text in texts), spec.title
