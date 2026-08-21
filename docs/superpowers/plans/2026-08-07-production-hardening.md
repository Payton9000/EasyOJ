# EasyOJ Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden EasyOJ for bounded, local Windows LAN teaching use while improving OJ-style usability, account safety, deployment simplicity, judge isolation, and regression coverage.

**Architecture:** Keep the Flask/SQLite application and replace unsafe edges with focused services: centralized account validation/rate limiting, CSRF-protected browser writes, a fail-closed process policy, a language-adapter compiler/executor path, and a Tkinter Windows deployment wizard. Judge workers remain process-based and scale only within a CPU/memory cap.

**Tech Stack:** Python 3.10+, Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF, pytest, Ruff, Tkinter, Windows AppContainer/Job Object through pywin32.

## Global Constraints

- Target deployment is a single Windows machine on a trusted school LAN; production evaluation must fail closed when the configured sandbox is unavailable.
- Compile and run commands must use project-local absolute toolchain paths and `shell=False`.
- Default judge parallelism is `max(1, min(cpu_count - 1, 8))`; tests and load checks must use explicit lower caps.
- Browser state-changing requests require CSRF tokens; API responses must not expose unlisted problem data or another user’s submissions.
- This workspace has no Git metadata, so commit steps are recorded as validation checkpoints but are not executed.

---

### Task 1: Establish Security and Schema Foundations

**Files:**
- Modify: `requirements.txt`, `app/config.py`, `app/__init__.py`
- Create: `app/utils/validation.py`, `app/utils/rate_limit.py`
- Modify: `app/models/user.py`
- Test: `tests/unit/test_validation.py`, `tests/unit/test_config_limits.py`

**Interfaces:**
- `validate_username(value) -> str` and `validate_email(value) -> str` return normalized values or raise `ValueError`.
- `LoginRateLimiter.allow(key, now=None) -> bool` and `.record_failure(key, now=None)` provide bounded in-process login throttling.
- `User` exposes `must_change_password`, `failed_login_count`, `locked_until`, and `last_login_at`.

- [ ] Write failing tests for invalid usernames/emails, password-length policy, bounded worker calculation, and rate-limit lockout.
- [ ] Run `python -m pytest tests/unit/test_validation.py tests/unit/test_config_limits.py -q`; verify failures are about missing validators/config behavior.
- [ ] Add validators, rate limiter, security cookie settings, `Flask-WTF` CSRF initialization, and SQLite column bootstrap for new user fields.
- [ ] Run the focused tests and then `python -m compileall -q app tests`; expect all focused tests to pass.

### Task 2: Make Authentication and Administration Safe

**Files:**
- Modify: `app/web/auth.py`, `app/utils/decorators.py`, `app/web/admin.py`, `app/api/__init__.py`
- Create: `app/services/account_service.py`
- Test: `tests/integration/test_auth_security.py`, `tests/integration/test_admin_safety.py`

**Interfaces:**
- `AccountService.register(...)`, `.authenticate(...)`, `.reset_password(...)`, and `.can_change_admin_state(...)` own account invariants and transaction rollback behavior.

- [ ] Write failing tests for duplicate normalized accounts, inactive login, lockout, CSRF rejection, safe logout, self-disable/self-demotion, last-admin protection, and one-time password reset display.
- [ ] Run each new test file and confirm the failures occur at the missing behavior.
- [ ] Route registration/login/admin actions through `AccountService`; add CSRF fields to every browser POST form; make logout POST-only; return JSON 401/403 consistently for API requests.
- [ ] Add safe redirect handling, transaction rollback on `IntegrityError`, forced password change state, and generic login failure messages.
- [ ] Run focused auth/admin tests and the existing API tests; fix behavior without weakening assertions.

### Task 3: Harden the Judge Policy and Preserve Multi-Core Throughput

**Files:**
- Modify: `app/judge/engine.py`, `app/judge/compiler.py`, `app/judge/executor.py`, `app/judge/sandbox.py`, `app/utils/security.py`, `app/utils/file_utils.py`
- Test: `tests/unit/test_judge_policy.py`, `tests/unit/test_compiler_commands.py`, `tests/integration/test_judge_safety.py`

**Interfaces:**
- `JudgePolicy.from_config(config)` returns validated limits and worker count.
- `Compiler.compile(...)` and `Executor.execute(...)` both use the same sandbox policy; neither may silently fall back to unsandboxed production execution.

- [ ] Write failing tests for capped worker count, absolute command paths, shell-disabled execution, rejection when sandbox support is unavailable, output truncation, timeout, memory limit, and process-tree cleanup.
- [ ] Run focused tests and confirm policy/sandbox failures are real missing behavior.
- [ ] Add `JudgePolicy`, cap worker creation, reject invalid limits, and use a bounded queue with consistent submission/task rollback.
- [ ] Route C++/Java compilation through the sandbox runner, preserve project-local toolchain paths, minimize environment variables, and apply Job Object limits to compiler children and runtime children.
- [ ] Keep blacklist scanning as advisory validation only; cap source, test input, output, log, and workspace sizes and make cleanup path-safe.
- [ ] Run focused safety tests with sub-second limits and at most two workers; then run existing judge-limit tests.

### Task 4: Make APIs and User Flows Predictable

**Files:**
- Modify: `app/api/endpoints.py`, `app/web/problems.py`, `app/web/contests.py`, `app/templates/submissions/detail.html`
- Test: `tests/integration/test_api_security.py`, `tests/integration/test_submission_failures.py`, `tests/e2e/test_user_flows.py`

- [ ] Write failing tests for unpublished problem filtering, bounded `per_page`, ownership checks, queue-full rollback, duplicate submission handling, invalid contest transitions, and stable error responses.
- [ ] Run the focused tests and confirm current leaks/rollback gaps are reproduced.
- [ ] Add shared pagination parsing, consistent JSON error envelopes, public visibility filters, transaction rollback, and idempotent submission enqueue behavior.
- [ ] Make status, retry, rejudge, and contest actions display explicit next steps and preserve form input after validation errors.
- [ ] Run all API, contest, and submission tests.

### Task 5: Replace the Visual Layer With a Conventional OJ UI

**Files:**
- Create: `app/static/css/site.css`, `app/templates/_macros.html`
- Modify: `app/templates/base.html`, `app/templates/admin/admin_base.html`, `app/templates/auth/*.html`, `app/templates/problems/*.html`, `app/templates/contests/*.html`, `app/templates/submissions/*.html`, `app/templates/admin/*.html`
- Test: `tests/e2e/test_ui_contract.py`

- [ ] Write failing template tests for a shared navigation, visible validation errors, CSRF fields, status classes, responsive tables, and no theme-toggle/gradient UI.
- [ ] Run the focused template tests and confirm the current templates violate the contract.
- [ ] Move styles into `site.css`, remove dark-theme script and decorative gradients/emojis, standardize buttons/forms/tables/status badges, and add a compact admin navigation.
- [ ] Use macros for CSRF fields, flash messages, pagination, and empty states; ensure every list page has a clear filter/reset path.
- [ ] Run the UI contract tests and render key routes with Flask’s test client for 200/redirect/403 behavior.

### Task 6: Add a Windows-Only Local Deployment Wizard

**Files:**
- Create: `scripts/deploy/windows/deploy_core.py`, `scripts/deploy/windows/deploy_gui.py`, `scripts/deploy/windows/start_server.ps1`
- Modify: `scripts/deploy/windows/setup_toolchain.ps1`, `.env.example`, `README.md`, `scripts/deploy/README.md`
- Test: `tests/unit/test_deploy_core.py`, `tests/e2e/test_deploy_smoke.py`

- [ ] Write failing tests for project-root detection, local interpreter/compiler path discovery, safe `.env` generation, worker-limit defaults, and idempotent setup steps.
- [ ] Run the unit tests without downloading toolchains; confirm missing deployment helpers fail as expected.
- [ ] Implement a Tkinter wizard with explicit stages, progress/error text, cancellation, disk-space checks, local path validation, and a bounded download/extract flow; never mutate outside the project root.
- [ ] Add checksum-aware toolchain downloads, local `.venv` installation, database initialization/backup, LAN bind configuration, and a start script using absolute paths.
- [ ] Run the deployment core tests, PowerShell syntax checks, and a no-download GUI smoke test.

### Task 7: Add Safe Deep Verification and Documentation

**Files:**
- Create: `tests/safety/test_bounded_execution.py`, `tests/load/safe_load_test.py`, `scripts/verify_windows.py`, `docs/WINDOWS_DEPLOYMENT.md`
- Modify: `pyproject.toml`, `AGENTS.md`

- [ ] Write failing tests for the safe-load command refusing unbounded duration, users, workers, or queue settings.
- [ ] Implement a short load harness with hard maximums (30 seconds, 12 users, 2 workers, 100 submissions), resource snapshots, and guaranteed cleanup.
- [ ] Add `scripts/verify_windows.py` to run compileall, Ruff, pytest, local toolchain checks, and sandbox capability checks without starting an unbounded workload.
- [ ] Run the complete suite, bounded safety suite, Ruff check/format verification, and Windows-only checks where supported.
- [ ] Update contributor and deployment documentation with the LAN threat model, backup procedure, local toolchain behavior, and safe test commands.

## Final Review Checklist

- [ ] `python -m compileall -q app tests scripts`
- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `python -m pytest -q`
- [ ] `python scripts/verify_windows.py --safe`
- [ ] Confirm no test starts more than two judge workers or runs longer than 30 seconds by default.
