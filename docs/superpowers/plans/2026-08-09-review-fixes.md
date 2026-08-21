# EasyOJ Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the production-readiness defects reproduced during review without weakening EasyOJ's Windows sandbox or running unsafe load tests.

**Architecture:** Keep the existing Flask/SQLite single-host design. Centralize contest submission policy and queue-failure state transitions, register SQLite connection settings per app engine, store contest timestamps as naive UTC while rendering deployment-machine local time, and preserve academic history by rejecting destructive deletes when submissions exist.

**Tech Stack:** Python 3.10+, Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF, SQLite, pytest, Ruff, Windows AppContainer/Job Object.

## Global Constraints

- Target a trusted school LAN on a daily-use Windows machine; do not introduce Redis, external workers, global toolchains, or non-Windows deployment dependencies.
- Preserve fail-closed AppContainer and Job Object behavior.
- Use bounded focused tests and the existing safe verification gate; never run soak/manual stress tools.
- This checkout has no Git history, so commits and worktrees are not part of execution.
- Implement every behavioral change test-first and verify each regression test fails for the reproduced defect before changing production code.

---

### Task 1: Enforce Contest Submission Isolation

**Files:**
- Create: `app/services/submission_service.py`
- Modify: `app/api/endpoints.py`, `app/web/problems.py`
- Test: `tests/integration/test_submit_bypass.py`, `tests/integration/test_api_security.py`

- [x] Add failing tests proving a participant cannot submit an active contest problem through `/api/submit`, malformed JSON values return 400 instead of 500, and legacy unscoped submissions do not expose expected answers during the contest.
- [x] Add one shared active-contest lookup and use it in browser/API submission and answer-visibility paths.
- [x] Return a stable 409 API response with the contest ID and create no submission when contest context is required.
- [x] Run the focused API and bypass tests.

### Task 2: Make Sealed Ranklists Actually Private

**Files:**
- Modify: `app/web/contests.py`, `app/templates/contests/ranklist.html`
- Test: `tests/integration/test_contest_integrity.py`

- [x] Add failing participant/anonymous tests proving rank rows are absent while a running contest is sealed, plus an ended-contest control.
- [x] Skip ranklist computation/rendering for non-admin viewers until the contest ends; keep an explicit sealed notice.
- [x] Run the focused contest-integrity tests.

### Task 3: Round-Trip Contest Times Correctly

**Files:**
- Create: `app/utils/time_utils.py`
- Modify: `app/__init__.py`, `app/web/admin.py`
- Modify: contest/admin templates that render contest timestamps
- Test: `tests/unit/test_admin_time_utils.py`, `tests/integration/test_admin_contests.py`

- [x] Add failing tests for local-input → UTC-storage → local-form round trips and public local-time rendering.
- [x] Keep naive UTC in the database, add system-local conversion helpers/Jinja filters, and render `datetime-local` values through the converter.
- [x] Run focused time and contest-admin tests under a non-UTC test timezone where supported.

### Task 4: Apply SQLite Safety Settings to Every App Engine

**Files:**
- Modify: `app/__init__.py`
- Test: `tests/unit/test_sqlite_config.py`

- [x] Add a failing two-app regression proving both independent SQLite engines receive WAL, busy timeout, foreign-key enforcement, and normal synchronous mode.
- [x] Replace the process-global registration guard with per-app/per-engine registration.
- [x] Run the focused SQLite tests.

### Task 5: Preserve Submission History During Deletes

**Files:**
- Modify: `app/web/admin.py`
- Test: `tests/integration/test_admin_deletion_safety.py`

- [x] Add failing route tests for deleting a problem or contest that owns submissions with foreign keys enabled.
- [x] Reject those deletes before mutation and direct administrators to hide the problem/contest instead; retain current deletion for unused records.
- [x] Run focused deletion and admin tests.

### Task 6: Converge Queue Failures to a Terminal State

**Files:**
- Modify: `app/services/submission_service.py`, `app/web/problems.py`, `app/web/contests.py`, `app/api/endpoints.py`
- Test: `tests/integration/test_submission_failures.py`

- [x] Add failing browser and contest tests where the judge enqueue call raises or returns false.
- [x] Centralize enqueue handling so every committed submission becomes `Failed` with a safe operator-facing reason rather than remaining `Pending`.
- [x] Run focused submission-failure tests.

### Task 7: Narrow API CSRF and Complete Developer Setup

**Files:**
- Modify: `app/__init__.py`, `app/api/endpoints.py`, `requirements-dev.txt`, `AGENTS.md`
- Test: `tests/integration/test_api_csrf.py`

- [x] Add a failing test proving session-authenticated API mutations reject a missing CSRF header and accept a valid header.
- [x] Remove blueprint-wide CSRF exemption while preserving JSON error responses for CSRF failures.
- [x] Declare pytest in development requirements and update repository guidance for current worker/config behavior.
- [x] Run API CSRF tests and dependency/config checks.

### Task 8: Full Safe Verification

- [x] Run `python -m compileall -q app tests scripts`.
- [x] Run `ruff check app scripts tests` and `ruff format --check app scripts tests`.
- [x] Run the complete pytest suite.
- [x] Run `scripts/verify_windows.py --safe`, including real bounded AppContainer smoke submissions.
- [x] Confirm no development server, worker, or verification process remains running.
