# Bilingual Coding Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add complete fixed-text Chinese/English switching and a responsive LeetCode-style in-browser coding workspace.

**Architecture:** A dependency-free translation catalog is initialized by the app factory. Public and contest problem views share editor behavior, while a bounded practice-run service reuses the fail-closed compiler and executor.

**Tech Stack:** Flask/Jinja, vanilla JavaScript, CSS Grid/Flexbox, pytest, Windows AppContainer.

## Global Constraints

- Translate fixed UI only; render DB problem/contest/user text unchanged.
- No CDN, npm, global compiler, copied LeetCode assets, or external runtime.
- Run code through the existing fail-closed sandbox boundary.
- Custom input is capped at 32 KiB; source remains under the existing request/source limits.
- This checkout has no Git repository; omit commit commands.

---

### Task 1: Locale core

**Files:**
- Create: `app/i18n/__init__.py`
- Create: `app/i18n/catalogs.py`
- Modify: `app/__init__.py`
- Create: `app/web/locale.py`
- Modify: `app/web/__init__.py`
- Test: `tests/unit/test_i18n.py`

**Interfaces:**
- Produces: `get_locale() -> str`, `translate(key: str, **values) -> str`, `init_i18n(app) -> None`.
- Produces: CSRF-protected `POST /language/<locale>` accepting `en` and `zh-CN`.

- [ ] Test default locale, browser preference, session override, unsupported locale rejection, interpolation, missing-key fallback, and `<html lang>`.
- [ ] Confirm RED; implement catalogs and app/Jinja registration.
- [ ] Run unit tests and Ruff.

### Task 2: Public, auth, contest, submission, and error translations

**Files:**
- Modify: `app/templates/base.html`
- Modify: `app/templates/auth/*.html`
- Modify: `app/templates/problems/*.html`
- Modify: `app/templates/contests/*.html`
- Modify: `app/templates/submissions/*.html`
- Modify: `app/templates/error.html`
- Modify: `app/web/auth.py`, `app/web/problems.py`, `app/web/contests.py`, `app/__init__.py`
- Test: `tests/e2e/test_i18n_ui.py`

- [ ] Add English and Chinese page-contract tests for nav, forms, flashes, status labels, contest actions, and error pages.
- [ ] Replace fixed strings with translation keys and keep variable DB values unchanged.
- [ ] Run the e2e contract and existing auth/contest tests.

### Task 3: Administration translations

**Files:**
- Modify: `app/templates/admin/*.html`
- Modify: `app/web/admin.py`
- Test: `tests/e2e/test_i18n_admin.py`

- [ ] Test both locales for dashboard, users, problems, contests, submissions, and judge status.
- [ ] Translate labels, actions, validation errors, and flashes without changing route behavior.
- [ ] Run admin i18n tests plus existing admin integration tests.

### Task 4: Shared coding workspace UI

**Files:**
- Create: `app/templates/problems/_workspace.html`
- Modify: `app/templates/problems/detail.html`
- Modify: `app/templates/contests/problem_detail.html`
- Create: `app/static/js/code_workspace.js`
- Modify: `app/static/css/site.css`
- Test: `tests/e2e/test_coding_workspace_contract.py`

**Interfaces:**
- Consumes: problem metadata and supported language mapping.
- Produces: DOM ids `code-editor`, `custom-input`, `run-code`, `submit-code`, `run-result`.

- [ ] Test two-pane markup, controls, translated labels, CSRF data, contest action URLs, and anonymous disabled state.
- [ ] Implement responsive statement/editor panes, sticky toolbar, result tabs, and restrained grey/white OJ styling.
- [ ] Implement local draft keys scoped by contest/problem/language, Tab indentation, `Ctrl+Enter` Run, and `Ctrl+Shift+Enter` Submit.
- [ ] Run UI contracts and inspect at desktop and narrow viewport.

### Task 5: Bounded custom-run service

**Files:**
- Create: `app/judge/practice.py`
- Modify: `app/config.py`
- Modify: `app/api/endpoints.py`
- Test: `tests/unit/test_practice_run.py`
- Test: `tests/integration/test_api_practice_run.py`

**Interfaces:**
- Produces: `PracticeRunResult(status, output, error, time_used, memory_used)`.
- Produces: `PracticeRunService.run(language, code, input_data, problem) -> PracticeRunResult`.
- Produces: `POST /api/run/<problem_id>` JSON endpoint.

- [ ] Test unsupported language, oversized input, semaphore saturation, compile error, timeout, output cap, unauthenticated access, CSRF, and successful Python run.
- [ ] Confirm RED; implement one-slot `BoundedSemaphore`, unique temporary workspace, compiler call, one executor call, and unconditional cleanup.
- [ ] Register one service per Flask app so worker processes do not share unsafe thread state.
- [ ] Return 429 for busy, 400 for validation, and 200 with execution status for completed runs.
- [ ] Run targeted tests and judge safety tests.

### Task 6: Workspace integration and browser verification

**Files:**
- Modify: `app/static/js/code_workspace.js`
- Modify: `tests/e2e/test_coding_workspace_contract.py`

- [ ] Add mocked-fetch tests/contract assertions for Run result rendering and duplicate-click prevention.
- [ ] Wire Run JSON with `X-CSRFToken`; keep Submit as the existing form path.
- [ ] Restart the development server and verify public problem and contest workspace in both locales.
- [ ] Submit one accepted Python solution and run one custom input through the visible workspace.
