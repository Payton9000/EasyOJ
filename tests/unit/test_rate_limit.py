from datetime import datetime
from datetime import timedelta

from app.utils.rate_limit import BoundedWindowLimiter
from app.utils.rate_limit import LoginRateLimiter


def test_login_rate_limiter_blocks_after_consecutive_failures():
    limiter = LoginRateLimiter(max_failures=2, lockout_seconds=60)
    now = datetime(2026, 1, 1, 12, 0, 0)

    assert limiter.allow('user@example.com', now=now) is True
    limiter.record_failure('user@example.com', now=now)
    limiter.record_failure('user@example.com', now=now)

    assert limiter.allow('user@example.com', now=now) is False
    assert limiter.allow('user@example.com', now=now + timedelta(seconds=61)) is True


def test_success_clears_login_failures():
    limiter = LoginRateLimiter(max_failures=2, lockout_seconds=60)
    now = datetime(2026, 1, 1, 12, 0, 0)

    limiter.record_failure('user@example.com', now=now)
    limiter.record_success('user@example.com')

    assert limiter.allow('user@example.com', now=now) is True


def test_rate_limiter_bounds_unknown_username_state():
    limiter = LoginRateLimiter(max_failures=3, max_entries=2)
    now = datetime(2026, 1, 1, 12, 0, 0)

    for username in ('one', 'two', 'three'):
        limiter.record_failure(username, now=now)

    assert len(limiter._states) <= 2


def test_bounded_window_limiter_caps_actions_and_resets():
    limiter = BoundedWindowLimiter(max_events=2, window_seconds=10, max_entries=2)
    now = datetime(2026, 1, 1, 12, 0, 0)

    assert limiter.allow('student', now=now)
    assert limiter.allow('student', now=now + timedelta(seconds=1))
    assert not limiter.allow('student', now=now + timedelta(seconds=2))
    assert limiter.allow('student', now=now + timedelta(seconds=11))


def test_bounded_window_limiter_does_not_grow_past_entry_cap():
    limiter = BoundedWindowLimiter(max_events=1, window_seconds=60, max_entries=2)
    now = datetime(2026, 1, 1, 12, 0, 0)

    for index in range(5):
        assert limiter.allow(f'user-{index}', now=now + timedelta(seconds=index))

    assert len(limiter._states) == 2
