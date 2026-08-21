# Problem Bank Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 30 validated problems, repair malformed newline data, and provide a safe idempotent problem-only importer.

**Architecture:** Four independent pack modules produce immutable problem specifications. A central validator rejects malformed catalogs before an importer updates the existing `Problem` rows and testcase directory layout.

**Tech Stack:** Python 3.10, Flask-SQLAlchemy, SQLite, pytest, Ruff.

## Global Constraints

- All delegated workers use `gpt-5.6-luna`.
- Produce exactly 30 new problems: 10 easy, 10 medium, 10 hard.
- Every new problem has at least 10 deterministic hidden cases and real newline characters.
- The importer never creates users, changes passwords, or creates contests.
- Do not run soak or manual stress tests.
- This checkout has no Git repository; omit commit commands and record test evidence instead.

---

### Task 1: Catalog schema and validation

**Files:**
- Create: `problem_bank/__init__.py`
- Create: `problem_bank/schema.py`
- Create: `problem_bank/validation.py`
- Test: `tests/unit/test_problem_bank_validation.py`

**Interfaces:**
- Produces: `TestCase(input_data: str, expected_output: str)` and `ProblemSpec(...)` frozen dataclasses.
- Produces: `validate_catalog(specs: Sequence[ProblemSpec]) -> None`.

- [ ] Write tests proving duplicate titles, literal `chr(92) + 'n'`, fewer than 10 cases, invalid difficulty, and oversized case data raise `ValueError`.
- [ ] Run `.venv\Scripts\python.exe -m pytest -q tests\unit\test_problem_bank_validation.py` and confirm RED.
- [ ] Implement dataclasses and validation with 256 KiB per input/output and known difficulty `{easy, medium, hard}`.
- [ ] Run the test and Ruff on `problem_bank tests\unit\test_problem_bank_validation.py` and confirm GREEN.

### Task 2: Repair legacy newline generation

**Files:**
- Modify: `tests/seed_demo_data.py`
- Test: `tests/unit/test_seed_demo_data.py`

**Interfaces:**
- Consumes: existing `build_problem_specs()` dictionaries.
- Produces: all sample inputs and generated cases with actual line-feed characters.

- [ ] Add a regression test that asserts 16 existing specs, no literal backslash-`n` in samples/cases, and real newlines for all multiline samples.
- [ ] Run the single test and confirm it reports the current 10 sample and 98 case failures.
- [ ] Replace only the double-escaped newline literals at their source.
- [ ] Run the regression test and confirm GREEN.

### Task 3: Foundations pack (7 easy)

**Files:**
- Create: `problem_bank/packs/__init__.py`
- Create: `problem_bank/packs/foundations.py`
- Test: `tests/unit/test_problem_pack_foundations.py`

**Interfaces:**
- Produces: `get_specs() -> tuple[ProblemSpec, ...]` with exactly seven easy problems.

- [ ] Write a contract test for count, difficulty, unique title, valid catalog, and expected outputs for every case.
- [ ] Implement seven original introductory problems covering arithmetic, conditions, loops, simulation, and basic arrays.
- [ ] Include boundary values, negatives where allowed, singleton cases, and maximum safe cases.
- [ ] Run the pack test and Ruff.

### Task 4: Arrays and strings pack (3 easy, 4 medium)

**Files:**
- Create: `problem_bank/packs/arrays_strings.py`
- Test: `tests/unit/test_problem_pack_arrays_strings.py`

**Interfaces:**
- Produces: `get_specs() -> tuple[ProblemSpec, ...]` with seven problems.

- [ ] Write the same catalog contract plus an exact `{easy: 3, medium: 4}` assertion.
- [ ] Implement original array/string problems with deterministic reference functions and at least 10 cases each.
- [ ] Include whitespace, duplicate, empty-equivalent/minimum, Unicode-free token, and upper-bound cases as applicable.
- [ ] Run the pack test and Ruff.

### Task 5: Algorithms pack (6 medium, 2 hard)

**Files:**
- Create: `problem_bank/packs/algorithms.py`
- Test: `tests/unit/test_problem_pack_algorithms.py`

**Interfaces:**
- Produces: `get_specs() -> tuple[ProblemSpec, ...]` with eight problems.

- [ ] Test exact count/distribution and reference outputs.
- [ ] Implement search, greedy, prefix/difference, graph, and dynamic-programming problems without duplicating existing titles.
- [ ] Bound generated cases so catalog validation and tests finish in under five seconds.
- [ ] Run the pack test and Ruff.

### Task 6: Advanced pack (8 hard)

**Files:**
- Create: `problem_bank/packs/advanced.py`
- Test: `tests/unit/test_problem_pack_advanced.py`

**Interfaces:**
- Produces: `get_specs() -> tuple[ProblemSpec, ...]` with eight hard problems.

- [ ] Test count, difficulty, validation, and deterministic output generation.
- [ ] Implement graph, DP, data-structure, and combinatorial problems suitable for undergraduate coursework.
- [ ] Ensure worst cases are meaningful but cannot exhaust host memory during validation.
- [ ] Run the pack test and Ruff.

### Task 7: Catalog aggregation and safe importer

**Files:**
- Create: `problem_bank/catalog.py`
- Create: `problem_bank/importer.py`
- Create: `scripts/seed_problem_bank.py`
- Modify: `tests/seed_demo_data.py`
- Test: `tests/integration/test_problem_bank_import.py`

**Interfaces:**
- Produces: `get_new_problem_specs() -> tuple[ProblemSpec, ...]`.
- Produces: `import_problem_bank(app, specs=None) -> ImportSummary(created, updated, testcase_files)`.

- [ ] Test first import creates 30 rows, second import creates zero, existing users remain byte-for-byte unchanged, and every problem has at least 10 numbered input/output pairs.
- [ ] Confirm RED, then implement validate-before-write and a module-level file write lock.
- [ ] Stage each testcase pair as temporary files and replace atomically after all files are writable.
- [ ] Make `scripts/seed_problem_bank.py` print a summary and return non-zero without partial DB writes on validation failure.
- [ ] Run import tests, all problem-bank tests, Ruff, and format check.

### Task 8: Live data repair and verification

**Files:**
- Modify through importer only: `data/database.db`, `data/problems/<new-id>/testcases/*`

- [ ] Back up `data/database.db` to a timestamped file in `data/backups/` without touching unrelated data.
- [ ] Run `.venv\Scripts\python.exe scripts\seed_problem_bank.py` once.
- [ ] Query SQLite and assert 46 public catalog problems, 30 newly titled rows, zero sample inputs containing `char(92)||'n'`, and at least 10 cases for each new problem.
- [ ] Open representative easy, medium, and hard pages and verify real sample line breaks.
