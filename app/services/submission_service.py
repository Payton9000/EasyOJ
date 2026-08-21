from datetime import datetime

from flask import current_app
from sqlalchemy import and_

from app import db
from app.models.contest import Contest
from app.models.contest_participant import ContestParticipant
from app.models.contest_problem import ContestProblem
from app.models.submission import Submission

QUEUE_UNAVAILABLE_MESSAGE = 'Judge queue is full or unavailable.'


def find_active_contest_problem(problem_id, user_id, now=None):
    """Return the active contest-problem row that owns this user's submission path."""
    if not user_id:
        return None

    now = now or datetime.utcnow()
    return (
        ContestProblem.query.join(Contest, Contest.id == ContestProblem.contest_id)
        .join(
            ContestParticipant,
            and_(
                ContestParticipant.contest_id == ContestProblem.contest_id,
                ContestParticipant.user_id == user_id,
            ),
        )
        .filter(
            ContestProblem.problem_id == problem_id,
            Contest.start_time <= now,
            Contest.end_time > now,
            ContestParticipant.is_disqualified.is_(False),
        )
        .order_by(Contest.start_time.asc(), Contest.id.asc())
        .first()
    )


def submission_is_in_active_contest(submission, now=None):
    """Protect both scoped submissions and legacy rows missing ``contest_id``."""
    now = now or datetime.utcnow()
    if submission.contest_id:
        contest = db.session.get(Contest, submission.contest_id)
        return bool(contest and contest.start_time <= now < contest.end_time)

    return find_active_contest_problem(submission.problem_id, submission.user_id, now) is not None


def enqueue_submission(submission):
    """Enqueue a committed submission and converge any failure to ``Failed``."""
    # Import lazily: importing the service must not initialize the judge blueprint
    # through app.judge.__init__, which would otherwise create a module cycle.
    from app.judge.admission import admission_slot

    submission_id = submission.id
    with admission_slot(submission.user_id) as admission:
        if not admission.accepted:
            persisted = db.session.get(Submission, submission_id)
            if persisted:
                persisted.status = 'Failed'
                persisted.error_message = QUEUE_UNAVAILABLE_MESSAGE
                db.session.commit()
            return False

        try:
            success = current_app.judge_engine.submit_judge_task(submission_id)
        except Exception:
            current_app.logger.exception('Failed to enqueue submission %s', submission_id)
            db.session.rollback()
            success = False

        if success:
            return True

        persisted = db.session.get(Submission, submission_id)
        if persisted:
            persisted.status = 'Failed'
            persisted.error_message = QUEUE_UNAVAILABLE_MESSAGE
            db.session.commit()
        return False
