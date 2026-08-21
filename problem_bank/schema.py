from dataclasses import dataclass


@dataclass(frozen=True)
class TestCase:
    input_data: str
    expected_output: str


@dataclass(frozen=True)
class ProblemSpec:
    title: str
    difficulty: str
    time_limit: int
    memory_limit: int
    source: str
    description: str
    input_description: str
    output_description: str
    sample_input: str
    sample_output: str
    cases: tuple[TestCase, ...]
