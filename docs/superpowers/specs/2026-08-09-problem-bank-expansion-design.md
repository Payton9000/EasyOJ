# Problem Bank Expansion Design

## Goal

Add 30 production-ready problems and repair literal `\n` characters without coupling
problem content to demo users or contests.

## Structure

Create a project-local `problem_bank` package with a small schema, catalog validator,
idempotent importer, and four independent packs. The packs contain 7, 7, 8, and 8
problems; together they provide 10 easy, 10 medium, and 10 hard problems. Each problem
contains a single-language statement, limits, sample data with real newline characters,
and at least 10 deterministic hidden test cases.

The importer only updates problems and testcase files. It never creates users, resets
passwords, or creates contests. Existing demo seeding may consume the same catalog but
remains a separate operator action.

## Validation and Safety

Before a database write, validate unique titles, known difficulties, positive limits,
case counts, UTF-8 size limits, absence of literal backslash-`n` sequences, and exact
reference outputs. File replacement is serialized and staged so a failed validation
cannot leave half-written cases. Large cases remain bounded for a daily-use machine.

## Compatibility

The existing `Problem` model and `data/problems/<id>/testcases` layout remain unchanged.
The repair path updates the 10 affected samples and prevents the 98 malformed generated
cases from being written in future runs.
