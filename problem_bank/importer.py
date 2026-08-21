"""Idempotent import and repair helpers for the local problem bank."""

import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from problem_bank.validation import validate_catalog

_IMPORT_LOCK = threading.RLock()
_PROBLEM_TEXT_FIELDS = (
    'description',
    'input_description',
    'output_description',
    'sample_input',
    'sample_output',
)
_LITERAL_NEWLINE = chr(92) + 'n'


@dataclass(frozen=True)
class ImportSummary:
    created: int = 0
    updated: int = 0
    repaired_problems: int = 0
    repaired_files: int = 0


def _normalise_text(value):
    """Convert the historical literal ``\\n`` encoding to a real newline."""
    if not isinstance(value, str):
        return value
    return value.replace(_LITERAL_NEWLINE, '\n')


def _canonical_case_text(value):
    value = _normalise_text(value)
    return value.rstrip('\r\n') + '\n'


def _write_case_files(base_dir, problem_id, cases):
    problem_dir = Path(base_dir) / 'data' / 'problems' / str(problem_id)
    problem_dir.mkdir(parents=True, exist_ok=True)
    target_dir = problem_dir / 'testcases'
    stage_dir = Path(tempfile.mkdtemp(prefix='.testcases-', dir=str(problem_dir)))
    try:
        for index, case in enumerate(cases, 1):
            (stage_dir / f'{index}.in').write_text(
                _canonical_case_text(case.input_data), encoding='utf-8', newline='\n'
            )
            (stage_dir / f'{index}.out').write_text(
                _canonical_case_text(case.expected_output), encoding='utf-8', newline='\n'
            )

        target_dir.mkdir(parents=True, exist_ok=True)
        staged_names = {path.name for path in stage_dir.iterdir()}
        # Replace numbered files only after every staged pair is complete.
        for staged in sorted(stage_dir.iterdir()):
            os.replace(staged, target_dir / staged.name)
        for old_file in target_dir.iterdir():
            if old_file.suffix in {'.in', '.out'} and old_file.name not in staged_names:
                old_file.unlink()
    finally:
        for leftover in stage_dir.iterdir():
            leftover.unlink(missing_ok=True)
        stage_dir.rmdir()


def repair_legacy_problem_data(base_dir, problems):
    """Repair old DB/file values that contain a literal backslash-n sequence."""
    repaired_problems = 0
    repaired_files = 0
    for problem in problems:
        changed = False
        for field_name in _PROBLEM_TEXT_FIELDS:
            value = getattr(problem, field_name, None)
            normalised = _normalise_text(value)
            if normalised != value:
                setattr(problem, field_name, normalised)
                changed = True
        if changed:
            repaired_problems += 1

        testcase_dir = Path(base_dir) / 'data' / 'problems' / str(problem.id) / 'testcases'
        if not testcase_dir.is_dir():
            continue
        for path in testcase_dir.iterdir():
            if path.suffix not in {'.in', '.out'} or not path.is_file():
                continue
            try:
                value = path.read_text(encoding='utf-8')
            except (OSError, UnicodeError):
                continue
            normalised = _normalise_text(value)
            if normalised != value:
                path.write_text(normalised, encoding='utf-8', newline='\n')
                repaired_files += 1
    return repaired_problems, repaired_files


def import_problem_specs(app, specs, created_by=None, repair_legacy=True):
    """Import validated specs without touching users, contests, or submissions."""
    validate_catalog(specs)
    from app import db
    from app.models.problem import Problem

    with _IMPORT_LOCK:
        created = 0
        updated = 0
        with app.app_context():
            existing_problems = Problem.query.all()
            repaired_problems = repaired_files = 0
            if repair_legacy:
                repaired_problems, repaired_files = repair_legacy_problem_data(
                    app.config['BASE_DIR'], existing_problems
                )

            for spec in specs:
                problem = Problem.query.filter_by(title=spec.title).first()
                if problem is None:
                    problem = Problem(title=spec.title)
                    db.session.add(problem)
                    created += 1
                else:
                    updated += 1

                problem.description = spec.description
                problem.input_description = spec.input_description
                problem.output_description = spec.output_description
                problem.sample_input = spec.sample_input
                problem.sample_output = spec.sample_output
                problem.time_limit = spec.time_limit
                problem.memory_limit = spec.memory_limit
                problem.difficulty = spec.difficulty
                problem.source = spec.source
                problem.is_public = True
                if created_by is not None:
                    problem.created_by = created_by
                db.session.flush()
                _write_case_files(app.config['BASE_DIR'], problem.id, spec.cases)

            db.session.commit()
            return ImportSummary(
                created=created,
                updated=updated,
                repaired_problems=repaired_problems,
                repaired_files=repaired_files,
            )
