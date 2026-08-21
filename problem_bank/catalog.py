"""The built-in problem catalog shipped with EasyOJ."""

from problem_bank.packs.advanced import get_specs as get_advanced_specs
from problem_bank.packs.algorithms import get_specs as get_algorithm_specs
from problem_bank.packs.arrays_strings import get_specs as get_arrays_strings_specs
from problem_bank.packs.foundations import get_specs as get_foundation_specs
from problem_bank.schema import ProblemSpec
from problem_bank.validation import validate_catalog


def get_specs() -> tuple[ProblemSpec, ...]:
    """Return the 30 built-in problems in a stable, difficulty-grouped order."""
    specs = (
        *get_foundation_specs(),
        *get_arrays_strings_specs(),
        *get_algorithm_specs(),
        *get_advanced_specs(),
    )
    validate_catalog(specs)
    return specs
