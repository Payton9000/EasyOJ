from tests.seed_demo_data import build_problem_specs


def test_seed_problem_specs_use_real_newlines_in_samples_and_cases():
    specs = build_problem_specs()
    literal_escape = chr(92) + 'n'

    assert len(specs) == 16
    assert all(literal_escape not in spec['sample_input'] for spec in specs)
    assert all(
        literal_escape not in input_data
        for spec in specs
        for input_data, _expected_output in spec['cases']
    )

    multiline_samples = [spec['sample_input'] for spec in specs if '\n' in spec['sample_input']]
    multiline_cases = [
        input_data
        for spec in specs
        for input_data, _expected_output in spec['cases']
        if '\n' in input_data
    ]
    assert len(multiline_samples) == 10
    assert len(multiline_cases) == 98


def test_lnds_sample_preserves_expected_line_structure():
    spec = next(
        item
        for item in build_problem_specs()
        if item['title'] == 'Longest Nondecreasing Subsequence'
    )

    assert spec['sample_input'].splitlines() == ['6', '3 1 2 2 2 4']
    assert spec['sample_output'] == '5'
