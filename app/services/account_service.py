import secrets
import string
from datetime import datetime
from datetime import timedelta

from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.user import User
from app.utils.rate_limit import LoginRateLimiter
from app.utils.validation import validate_email
from app.utils.validation import validate_password
from app.utils.validation import validate_username


class AccountService:
    @staticmethod
    def _limiter():
        limiter = current_app.extensions.get('login_rate_limiter')
        if limiter is None:
            limiter = LoginRateLimiter(
                max_failures=current_app.config.get('LOGIN_MAX_FAILURES', 5),
                lockout_seconds=current_app.config.get('LOGIN_LOCKOUT_SECONDS', 60),
                window_seconds=current_app.config.get('LOGIN_FAILURE_WINDOW_SECONDS', 300),
                max_entries=current_app.config.get('LOGIN_RATE_MAX_ENTRIES', 10000),
            )
            current_app.extensions['login_rate_limiter'] = limiter
        return limiter

    @staticmethod
    def register(username, email, password):
        username = validate_username(username)
        email = validate_email(email)
        password = validate_password(password)

        # Legacy databases may contain mixed-case values created before the
        # normalized username policy.  Check case-insensitively before the
        # unique constraint so registration remains predictable across SQLite
        # and other database backends.
        existing = User.query.filter(
            (func.lower(User.username) == username) | (func.lower(User.email) == email)
        ).first()
        if existing:
            raise ValueError('Username or email is already registered.')

        user = User(username=username, email=email, role='user')
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            raise ValueError('Username or email is already registered.') from exc
        return user

    @classmethod
    def authenticate(cls, username, password):
        try:
            normalized_username = validate_username(username)
        except ValueError:
            return None

        limiter = cls._limiter()
        if not limiter.allow(normalized_username):
            return None

        user = User.query.filter(func.lower(User.username) == normalized_username).first()
        now = datetime.utcnow()
        if user and user.locked_until and user.locked_until > now:
            return None

        if user and user.locked_until and user.locked_until <= now:
            user.failed_login_count = max(0, (user.failed_login_count or 0) - 1)
            user.locked_until = None
            db.session.commit()

        valid = bool(user and user.is_active and user.check_password(password or ''))
        if valid:
            user.failed_login_count = 0
            user.locked_until = None
            user.last_login_at = now
            db.session.commit()
            limiter.record_success(normalized_username)
            return user

        limiter.record_failure(normalized_username, now=now)
        if user:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            max_failures = current_app.config.get('LOGIN_MAX_FAILURES', 5)
            if user.failed_login_count >= max_failures:
                user.locked_until = now + timedelta(
                    seconds=current_app.config.get('LOGIN_LOCKOUT_SECONDS', 60)
                )
            db.session.commit()
        return None

    @staticmethod
    def can_change_admin_state(target, actor, active=None, role=None):
        if not target or not actor or target.id == actor.id:
            return False

        demoting = role is not None and target.is_admin and role != 'admin'
        disabling = active is False and target.is_active
        if not target.is_admin or not (demoting or disabling):
            return True

        active_admins = User.query.filter_by(role='admin', is_active=True).count()
        return active_admins > 1

    @classmethod
    def toggle_active(cls, target, actor):
        next_active = not bool(target.is_active)
        if not cls.can_change_admin_state(target, actor, active=next_active):
            return False
        target.is_active = next_active
        db.session.commit()
        return True

    @classmethod
    def toggle_role(cls, target, actor):
        next_role = 'admin' if target.role != 'admin' else 'user'
        if not cls.can_change_admin_state(target, actor, role=next_role):
            return False
        target.role = next_role
        db.session.commit()
        return True

    @staticmethod
    def reset_password(target):
        alphabet = string.ascii_letters + string.digits
        temporary_password = ''.join(secrets.choice(alphabet) for _ in range(14))
        target.set_password(temporary_password)
        target.must_change_password = True
        target.failed_login_count = 0
        target.locked_until = None
        db.session.commit()
        return temporary_password

    @staticmethod
    def change_password(user, new_password, confirmation, current_password=None):
        if current_password is not None and not user.check_password(current_password):
            raise ValueError('Current password is incorrect.')
        if new_password != confirmation:
            raise ValueError('Passwords do not match.')
        user.set_password(validate_password(new_password))
        user.must_change_password = False
        user.failed_login_count = 0
        user.locked_until = None
        db.session.commit()
