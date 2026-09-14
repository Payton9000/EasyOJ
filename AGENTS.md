# Repository Guidelines

[English](AGENTS.md) · [中文](AGENTS_ZH.md)

## Project Structure & Module Organization

EasyOJ is a Windows-first Flask online judge for a trusted school LAN. Application code lives in `app/`: routes are in `app/web/` and `app/api/`, judge execution is in `app/judge/`, and templates/assets are under `app/templates/` and `app/static/`. CodeMirror source and tests live in `frontend/`; generated editor assets belong in `app/static/vendor/codemirror/`, while `frontend/node_modules/` stays untracked. The built-in catalog is in `problem_bank/`; runtime test points use `data/problems/<id>/testcases/<n>.in` and `<n>.out`. Tests are grouped under `tests/unit/`, `tests/integration/`, `tests/e2e/`, and bounded `tests/load/`.

## Build, Test, and Development Commands

Use the project-local environment on Windows:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe init_db.py
.venv\Scripts\python.exe run.py development
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check app scripts tests problem_bank
.venv\Scripts\ruff.exe format --check app scripts tests problem_bank
.venv\Scripts\python.exe scripts\verify_windows.py --safe
.venv\Scripts\python.exe scripts\verify_windows.py --safe --dev
pnpm --dir frontend test
pnpm --dir frontend run build
```

`init_db.py` creates the database and imports 30 built-in problems. Use `scripts/seed_problem_bank.py` to idempotently repair/reimport that catalog. Classroom `--safe` verification is toolchain plus AppContainer smoke; `--dev` also runs compileall, Ruff, and pytest.

## Coding Style & Naming Conventions

Target Python 3.10, four-space indentation, 100-character lines, single quotes, and Ruff-managed imports. Use `snake_case` for functions/modules, `PascalCase` for classes, and descriptive route/service names. Keep language commands as argument vectors; never introduce shell command strings. UI text belongs in both dictionaries in `app/i18n/catalogs.py`; problem statements remain single-language database content.

## Testing Guidelines

Name tests `test_<behavior>.py` and place the narrowest test first. Run a focused test during development, then the full suite. Every judge, account, contest, or sandbox change needs failure-path tests. Do not run `tests/load/soak_test.py` or manual stress tools without an explicit operator decision.

## Commit & Pull Request Guidelines

This checkout has no Git history. Use short imperative commits such as `Fix judge admission race`. Pull requests should explain user impact, list verification commands, link issues, and include screenshots for visible UI changes.

## Security & Configuration

Preserve fail-closed AppContainer and Job Object enforcement. Never commit `.env`, database files, temporary passwords, or submissions. Keep toolchains project-local and do not expose the production profile to the public internet.
