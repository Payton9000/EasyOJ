import calendar
import time
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from app.utils.time_utils import format_local_datetime
from app.utils.time_utils import format_local_datetime_input
from app.utils.time_utils import parse_local_datetime_to_utc
from app.web.admin import _parse_local_datetime_to_utc


def _true_utc(naive):
    return naive.astimezone(timezone.utc).replace(tzinfo=None)


def test_parse_local_datetime_to_utc_matches_local_offset():
    naive = datetime(2026, 6, 15, 12, 0)
    result = _parse_local_datetime_to_utc(naive.isoformat())
    expected_offset = calendar.timegm(naive.timetuple()) - time.mktime(naive.timetuple())
    assert result == naive - timedelta(seconds=expected_offset)
    assert result == _true_utc(naive)
    assert result.tzinfo is None


def test_parse_local_datetime_to_utc_winter_date():
    naive = datetime(2026, 1, 10, 9, 30)
    result = _parse_local_datetime_to_utc(naive.isoformat())
    expected_offset = calendar.timegm(naive.timetuple()) - time.mktime(naive.timetuple())
    assert result == naive - timedelta(seconds=expected_offset)
    assert result == _true_utc(naive)


def test_local_datetime_round_trip_uses_explicit_offset():
    china_standard_time = timezone(timedelta(hours=8))

    stored = parse_local_datetime_to_utc(
        '2035-06-15T09:30',
        local_timezone=china_standard_time,
    )

    assert stored == datetime(2035, 6, 15, 1, 30)
    assert format_local_datetime_input(stored, local_timezone=china_standard_time) == (
        '2035-06-15T09:30'
    )
    assert (
        format_local_datetime(
            stored,
            '%Y-%m-%d %H:%M',
            local_timezone=china_standard_time,
        )
        == '2035-06-15 09:30'
    )


def test_time_formatters_handle_empty_values():
    assert format_local_datetime(None) == ''
    assert format_local_datetime_input(None) == ''
