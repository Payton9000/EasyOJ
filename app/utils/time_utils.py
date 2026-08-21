from datetime import datetime
from datetime import timezone


def parse_local_datetime_to_utc(value, local_timezone=None):
    """Parse a browser ``datetime-local`` value into naive UTC for storage."""
    if not isinstance(value, str):
        raise TypeError('datetime value must be a string')

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        if local_timezone is None:
            parsed = parsed.astimezone()
        else:
            parsed = parsed.replace(tzinfo=local_timezone)

    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def utc_to_local_datetime(value, local_timezone=None):
    """Convert a stored naive UTC datetime to a naive local display value."""
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError('datetime value is required')

    if value.tzinfo is None:
        utc_value = value.replace(tzinfo=timezone.utc)
    else:
        utc_value = value.astimezone(timezone.utc)

    if local_timezone is None:
        local_value = utc_value.astimezone()
    else:
        local_value = utc_value.astimezone(local_timezone)
    return local_value.replace(tzinfo=None)


def format_local_datetime(value, fmt='%Y-%m-%d %H:%M', local_timezone=None):
    local_value = utc_to_local_datetime(value, local_timezone=local_timezone)
    return local_value.strftime(fmt) if local_value else ''


def format_local_datetime_input(value, local_timezone=None):
    return format_local_datetime(
        value,
        '%Y-%m-%dT%H:%M',
        local_timezone=local_timezone,
    )
