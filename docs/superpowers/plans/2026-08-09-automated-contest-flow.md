# Automated Contest Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a visible, bounded end-to-end demonstration of an admin-created contest with five concurrent student submitters.

**Architecture:** A loopback-only script starts an isolated app and drives real HTTP forms using independent cookie jars. It emits durable reports and optionally keeps the final scoreboard server available for browser inspection.

**Tech Stack:** Flask/Werkzeug local server, urllib, ThreadPoolExecutor, SQLite, pytest.

## Global Constraints

- Hard caps: five users, ten submissions, two judge workers, 120 seconds.
- Use a temporary `BASE_DIR`; never read or mutate the live admin account/database.
- The administrator must create the contest through HTTP forms.
- Preserve diagnostic artifacts on failure and stop all children on normal exit.
- This checkout has no Git repository; omit commit commands.

---

### Task 1: Bounded harness primitives

**Files:**
- Create: `scripts/demo_competition_flow.py`
- Test: `tests/unit/test_demo_competition_flow.py`

**Interfaces:**
- Produces: `FlowLimits(users=5, submissions=10, workers=2, timeout_s=120)` with validation.
- Produces: `HttpSession`, `LocalServer`, `StepResult`, and `write_report(report)`.

- [ ] Test hard-cap rejection, loopback bind, cookie isolation, report schema, and server cleanup.
- [ ] Confirm RED; implement only the primitives and argument parser (`--keep-open`, `--port`).
- [ ] Run unit tests and Ruff.

### Task 2: Admin and contest setup flow

**Files:**
- Modify: `scripts/demo_competition_flow.py`
- Test: `tests/integration/test_demo_contest_setup.py`

- [ ] Test temporary admin bootstrap, admin login, HTTP contest creation, problem attachment, and five participant additions.
- [ ] Seed one deterministic problem directly in the isolated database; create the contest itself only through HTTP.
- [ ] Parse CSRF tokens from every form and assert redirects plus resulting DB rows.
- [ ] Run the setup integration test.

### Task 3: Five-user concurrent submission flow

**Files:**
- Modify: `scripts/demo_competition_flow.py`
- Test: `tests/integration/test_demo_contest_concurrency.py`

- [ ] Test five independent logins and a barrier that releases exactly five POST submissions together.
- [ ] Poll each submission with a shared 120-second deadline; require terminal status and at least one AC per participant.
- [ ] Verify all rows carry the contest id and no user can view another user's private submission source.
- [ ] Run concurrency and existing contest isolation tests.

### Task 4: Ranklist, reporting, and keep-open mode

**Files:**
- Modify: `scripts/demo_competition_flow.py`
- Create: `tests/reports/competition_flow/.gitkeep`
- Test: `tests/e2e/test_demo_competition_report.py`

- [ ] Test ranklist contains five users, report contains each step/timing/submission transition, and credentials are redacted.
- [ ] Implement JSON/Markdown reports under `tests/reports/competition_flow` and print final ranklist URL.
- [ ] In `--keep-open`, wait for Ctrl+C while keeping only the isolated loopback server and judge workers alive.
- [ ] Run report tests and Ruff.

### Task 5: Execute visible demonstration

- [ ] Run the bounded script once without `--keep-open` and require overall PASS.
- [ ] Start it with `--keep-open --port 5001`, navigate the in-app browser to its final ranklist URL, and inspect the five rows.
- [ ] Preserve the latest JSON/Markdown report and provide the exact stop command/PID.
