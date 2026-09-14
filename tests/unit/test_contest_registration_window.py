from datetime import datetime
from datetime import timedelta

from app.models.contest import Contest


def _contest(**overrides):
    now = datetime.utcnow()
    values = {
        'title': 'Registration Window',
        'start_time': now - timedelta(minutes=10),
        'end_time': now + timedelta(minutes=10),
        'max_participants': 0,
        'close_registration_at_start': False,
        'created_by': 1,
    }
    values.update(overrides)
    return Contest(**values)


def test_running_contest_allows_late_registration_by_default():
    assert _contest().is_registration_open is True


def test_running_contest_can_close_registration_at_start():
    assert _contest(close_registration_at_start=True).is_registration_open is False


def test_pending_contest_stays_open_even_when_late_registration_is_forbidden():
    now = datetime.utcnow()
    contest = _contest(
        start_time=now + timedelta(hours=1),
        end_time=now + timedelta(hours=2),
        close_registration_at_start=True,
    )
    assert contest.is_registration_open is True


def test_ended_contest_rejects_registration():
    now = datetime.utcnow()
    contest = _contest(
        start_time=now - timedelta(hours=2),
        end_time=now - timedelta(minutes=1),
    )
    assert contest.is_registration_open is False
