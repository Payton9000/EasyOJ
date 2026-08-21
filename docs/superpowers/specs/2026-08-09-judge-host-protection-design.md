# Judge Host Protection Design

## Goal

Keep a school or home Windows computer responsive while several students submit code.

## Capacity Policy

Retain AppContainer and Job Object as the per-process security boundary. Add host-level
admission controls before DB queue creation and before worker dispatch. Safe defaults use
at most half of logical CPUs, cap workers at four, reserve one GiB of available memory,
pause dispatch above 85% host CPU, cap the persistent queue, and cap active submissions
per user. All values remain configurable with hard upper bounds.

Submission admission is fail-fast with a translated 429/503-style response when the
per-user or total queue cap is reached. Temporary host pressure pauses dispatch rather
than failing accepted work. The dispatcher resumes automatically after a short bounded
backoff. Existing stale-task recovery remains authoritative.

## Observability

The administrator judge page reports configured workers, live workers, DB queue depth,
in-process handoff depth, host CPU, available memory, and whether dispatch is paused.
Metrics are sampled with `psutil`; sampling failures fail safely to configured static
limits and never disable the sandbox.

## Testing

Unit tests cover limit calculation, admission boundaries, host-pressure decisions, and
worker-config propagation. Integration tests use mocked host metrics and tiny queues.
No unbounded soak test is run; verification uses the existing safe Windows gate.
