import re

USERNAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9_.-]{2,31}$')
EMAIL_PATTERN = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
MAX_EMAIL_LENGTH = 120
MIN_PASSWORD_LENGTH = 8


def validate_username(value):
    normalized = (value or '').strip().lower()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError(
            'Username must be 3-32 characters using lowercase letters, numbers, _, ., or -.'
        )
    return normalized


def validate_email(value):
    normalized = (value or '').strip().lower()
    if len(normalized) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError('Enter a valid email address.')
    return normalized


def validate_password(value):
    if not isinstance(value, str) or len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f'Password must be at least {MIN_PASSWORD_LENGTH} characters.')
    return value
