from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock

from flask import current_app
from sqlalchemy import func

from app import db
from app.models.judge_task import JudgeTask
from app.models.submission import Submission

_ACTIVE_STATUSES = ('Queued', 'Dispatched', 'Running')
_ADMISSION_LOCK = RLock()


@dataclass(frozen=True)
class AdmissionDecision:
    accepted: bool
    reason: str = ''
    retry_after: int = 0


def _active_count(*, user_id=None):
    query = (
        db.session.query(func.count(JudgeTask.id))
        .join(Submission, Submission.id == JudgeTask.submission_id)
        .filter(JudgeTask.status.in_(_ACTIVE_STATUSES))
    )
    if user_id is not None:
        query = query.filter(Submission.user_id == user_id)
    return int(query.scalar() or 0)


def check_submission_admission(user_id):
    total_limit = max(1, int(current_app.config.get('JUDGE_TOTAL_ACTIVE_MAX', 100)))
    user_limit = max(1, int(current_app.config.get('JUDGE_USER_ACTIVE_MAX', 3)))

    if _active_count() >= total_limit:
        return AdmissionDecision(False, 'system active submission limit reached', 15)
    if _active_count(user_id=user_id) >= user_limit:
        return AdmissionDecision(False, 'user active submission limit reached', 30)
    return AdmissionDecision(True)


@contextmanager
def admission_slot(user_id):
    """Serialize the admission check with the subsequent queue reservation."""
    with _ADMISSION_LOCK:
        yield check_submission_admission(user_id)
