# Judge Host Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound total judge load so a daily-use Windows host remains responsive under classroom submissions.

**Architecture:** A pure policy calculates safe worker limits, a host guard samples CPU/memory before dispatch, and admission checks bound persistent queued work per system and user. Per-submission AppContainer and Job Object limits remain unchanged.

**Tech Stack:** Python 3.10, multiprocessing spawn, psutil, SQLite, pytest.

## Global Constraints

- Default workers are at most half logical CPUs and never more than four.
- Reserve at least 1024 MiB available host memory and pause dispatch at 85% CPU.
- Sandbox fail-closed settings must be copied to every worker exactly as before.
- Tests mock host metrics; no unbounded load or soak execution.
- This checkout has no Git repository; omit commit commands.

---

### Task 1: Safe configuration defaults

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Test: `tests/unit/test_config_limits.py`

**Interfaces:**
- Produces: `calculate_judge_workers(cpu_count=None, cap=4) -> int`.
- Adds bounded keys `JUDGE_TOTAL_ACTIVE_MAX`, `JUDGE_USER_ACTIVE_MAX`, `JUDGE_HOST_MAX_CPU_PERCENT`, `JUDGE_HOST_MIN_AVAILABLE_MEMORY_MB`, `JUDGE_HOST_BACKOFF_MS`.

- [ ] Add table-driven tests for 1, 2, 4, 8, 32 CPUs, invalid environment strings, and hard caps.
- [ ] Confirm RED; change defaults and copy keys into `.env.example`.
- [ ] Run config tests and Ruff.

### Task 2: Host capacity guard

**Files:**
- Create: `app/judge/host_guard.py`
- Test: `tests/unit/test_host_guard.py`

**Interfaces:**
- Produces: `HostSnapshot(cpu_percent, available_memory_mb)`.
- Produces: `HostCapacityGuard.snapshot()` and `can_dispatch() -> tuple[bool, str]`.

- [ ] Test CPU high, memory low, both healthy, psutil exception, and a short cached sample window.
- [ ] Implement injected metric provider for deterministic tests and conservative fallback on sampling failure.
- [ ] Run unit tests and Ruff.

### Task 3: Queue admission limits

**Files:**
- Create: `app/judge/admission.py`
- Modify: `app/services/submission_service.py`
- Modify: `app/api/endpoints.py`
- Modify: `app/web/problems.py`
- Modify: `app/web/contests.py`
- Test: `tests/integration/test_judge_admission.py`

**Interfaces:**
- Produces: `AdmissionDecision(accepted: bool, reason: str, retry_after: int)`.
- Produces: `check_submission_admission(user_id: int) -> AdmissionDecision`.

- [ ] Test system cap, per-user cap, terminal tasks excluded, exact boundary, API response, and HTML flash behavior.
- [ ] Confirm RED; count `Queued`, `Dispatched`, and `Running` tasks using indexed joins.
- [ ] Check admission immediately before creating a submission and converge races to a queue-unavailable terminal state.
- [ ] Run admission, API submit, and contest integrity tests.

### Task 4: Pressure-aware dispatch and status

**Files:**
- Modify: `app/judge/engine.py`
- Modify: `app/judge/routes.py`
- Modify: `app/templates/admin/judge_status.html`
- Test: `tests/unit/test_judge_engine_dispatch.py`
- Test: `tests/integration/test_judge_status.py`

- [ ] Test that unhealthy host snapshots leave DB tasks Queued and healthy recovery dispatches them once.
- [ ] Inject one guard into `JudgeEngine`, apply bounded backoff, and expose the latest snapshot/pause reason.
- [ ] Add translated admin metrics without leaking process command lines or source code.
- [ ] Run dispatch, timeout, sandbox propagation, and status tests.

### Task 5: Safety verification

- [ ] Run `.venv\Scripts\python.exe -m pytest -q tests\unit tests\integration --maxfail=1`.
- [ ] Run Ruff check and format check.
- [ ] Run only bounded `tests\load\safe_load_test.py`; do not run soak/manual tools.
- [ ] Run `.venv\Scripts\python.exe scripts\verify_windows.py --safe` after all subsystems are integrated.
