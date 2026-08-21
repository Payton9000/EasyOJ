from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from threading import Lock


@dataclass
class _AttemptState:
    failures: int = 0
    first_failure_at: datetime | None = None
    locked_until: datetime | None = None


@dataclass
class _WindowState:
    window_started_at: datetime
    events: int = 0


class LoginRateLimiter:
    """Small, bounded in-process limiter for a single-machine LAN deployment."""

    def __init__(self, max_failures=5, lockout_seconds=60, window_seconds=300, max_entries=10000):
        self.max_failures = max(1, int(max_failures))
        self.lockout_seconds = max(1, int(lockout_seconds))
        self.window_seconds = max(self.lockout_seconds, int(window_seconds))
        self.max_entries = max(1, int(max_entries))
        self._states = {}
        self._lock = Lock()

    def _prune(self, now):
        expiry = timedelta(seconds=self.window_seconds)
        expired = [
            key
            for key, state in self._states.items()
            if state.first_failure_at
            and now - state.first_failure_at >= expiry
            and (not state.locked_until or now >= state.locked_until)
        ]
        for key in expired:
            self._states.pop(key, None)

        if len(self._states) > self.max_entries:
            oldest = sorted(
                self._states,
                key=lambda key: self._states[key].first_failure_at or datetime.min,
            )
            for key in oldest[: len(self._states) - self.max_entries]:
                self._states.pop(key, None)

    def allow(self, key, now=None):
        now = now or datetime.utcnow()
        normalized_key = str(key or '').strip().lower()
        if not normalized_key:
            return False

        with self._lock:
            self._prune(now)
            state = self._states.get(normalized_key)
            if state is None:
                return True
            if state.locked_until and now < state.locked_until:
                return False
            if state.first_failure_at and now - state.first_failure_at >= timedelta(
                seconds=self.window_seconds
            ):
                self._states.pop(normalized_key, None)
            return True

    def record_failure(self, key, now=None):
        now = now or datetime.utcnow()
        normalized_key = str(key or '').strip().lower()
        if not normalized_key:
            return

        with self._lock:
            self._prune(now)
            state = self._states.get(normalized_key)
            if state is None or (
                state.first_failure_at
                and now - state.first_failure_at >= timedelta(seconds=self.window_seconds)
            ):
                state = _AttemptState(first_failure_at=now)
                self._states[normalized_key] = state
            state.failures += 1
            if state.failures >= self.max_failures:
                state.locked_until = now + timedelta(seconds=self.lockout_seconds)
            self._prune(now)

    def record_success(self, key):
        normalized_key = str(key or '').strip().lower()
        if normalized_key:
            with self._lock:
                self._states.pop(normalized_key, None)


class BoundedWindowLimiter:
    """Bounded fixed-window limiter for actions such as submissions."""

    def __init__(self, max_events=30, window_seconds=60, max_entries=10000):
        self.max_events = max(1, int(max_events))
        self.window_seconds = max(1, int(window_seconds))
        self.max_entries = max(1, int(max_entries))
        self._states = {}
        self._lock = Lock()

    def _trim(self):
        if len(self._states) <= self.max_entries:
            return
        oldest = sorted(
            self._states,
            key=lambda key: self._states[key].window_started_at,
        )
        for key in oldest[: len(self._states) - self.max_entries]:
            self._states.pop(key, None)

    def _prune(self, now):
        expiry = timedelta(seconds=self.window_seconds)
        expired = [
            key for key, state in self._states.items() if now - state.window_started_at >= expiry
        ]
        for key in expired:
            self._states.pop(key, None)
        self._trim()

    def allow(self, key, now=None):
        now = now or datetime.utcnow()
        normalized_key = str(key or '').strip().lower()
        if not normalized_key:
            return False

        with self._lock:
            self._prune(now)
            state = self._states.get(normalized_key)
            if state is None:
                state = _WindowState(window_started_at=now)
                self._states[normalized_key] = state
                self._trim()
                state = self._states.get(normalized_key)
                if state is None:
                    return False
            if state.events >= self.max_events:
                return False
            state.events += 1
            return True


def submission_allowed():
    from flask import current_app
    from flask_login import current_user

    if current_user.is_admin:
        return True
    limiter = current_app.extensions.get('submission_rate_limiter')
    if limiter is None:
        candidate = BoundedWindowLimiter(
            max_events=current_app.config.get('SUBMISSION_RATE_MAX', 30),
            window_seconds=current_app.config.get('SUBMISSION_RATE_WINDOW_SECONDS', 60),
            max_entries=current_app.config.get('SUBMISSION_RATE_MAX_ENTRIES', 10000),
        )
        limiter = current_app.extensions.setdefault('submission_rate_limiter', candidate)
    return limiter.allow(str(current_user.id))
