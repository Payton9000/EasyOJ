import hashlib
import hmac
import secrets
from datetime import datetime

from flask import abort
from flask import current_app
from flask import flash
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask import url_for
from flask_login import current_user
from flask_login import login_required
from sqlalchemy import case
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash

from app import db
from app.i18n import translate as t
from app.models.contest import Contest
from app.models.contest_participant import ContestParticipant
from app.models.contest_problem import ContestProblem
from app.models.problem import Problem
from app.models.submission import Submission
from app.services.submission_service import enqueue_submission
from app.utils.rate_limit import submission_allowed
from app.utils.security import DangerousCodeError
from app.utils.security import sanitize_code
from app.web import web_bp


def _resolve_contest_problem(contest, alias):
    """Find a contest problem by alias, tolerating legacy rows with no alias.

    ``display_alias`` synthesises a label for rows stored before aliases became
    mandatory, so links built from it must resolve back to the same row.
    """
    wanted = (alias or '').strip().upper()
    if not wanted:
        return None
    exact = ContestProblem.query.filter_by(contest_id=contest.id, alias=wanted).first()
    if exact:
        return exact
    for candidate in ContestProblem.query.filter_by(contest_id=contest.id).all():
        if candidate.display_alias.upper() == wanted:
            return candidate
    return None


def _format_remaining(delta):
    """Coarse 'time left' label; empty string once the contest is over."""
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return ''
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        return f'{days}d {hours}h'
    if hours > 0:
        return f'{hours}h {minutes}m'
    if minutes > 0:
        return f'{minutes}m'
    return f'{seconds}s'


def _contest_password_matches(contest, candidate):
    """Verify a hashed password and upgrade one legacy plaintext row on success."""
    stored = contest.password or ''
    if not stored:
        return True

    is_hash = stored.startswith(('scrypt:', 'pbkdf2:', 'argon2:'))
    if is_hash:
        try:
            return check_password_hash(stored, candidate)
        except (TypeError, ValueError):
            return False

    matches = hmac.compare_digest(stored, candidate)
    if matches:
        contest.password = generate_password_hash(candidate)
        db.session.commit()
    return matches


def _submission_client_token():
    token = request.headers.get('Idempotency-Key') or request.form.get('idempotency_key')
    if token is None:
        token = request.args.get('idempotency_key')
    token = token.strip() if token else ''
    return token or None


def _scoped_client_token(token, language, code):
    """Bind an idempotency token to the exact payload it was issued for.

    The page issues one token per GET, so a student who edits their code and
    submits again reuses it. Without the payload in the key that genuine second
    attempt was silently discarded and they were shown the older verdict. Mixing
    the content in keeps double-clicks deduplicated while letting real edits through.
    """
    if not token:
        return None
    digest = hashlib.sha256(f'{language}\x00{code}'.encode()).hexdigest()[:24]
    return f'{token[:96]}:{digest}'


@web_bp.route('/contests')
def contest_list():
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str)

    query = Contest.query.filter(Contest.is_public.is_(True))
    if q:
        query = query.filter(Contest.title.ilike(f'%{q}%'))

    query = query.order_by(Contest.start_time.desc())
    paginated = query.paginate(page=page, per_page=20, error_out=False)

    contest_ids = [contest.id for contest in paginated.items]
    participant_counts = {}
    if contest_ids:
        rows = (
            db.session.query(
                ContestParticipant.contest_id,
                db.func.count(ContestParticipant.id),
            )
            .filter(
                ContestParticipant.contest_id.in_(contest_ids),
                ContestParticipant.is_disqualified.is_(False),
            )
            .group_by(ContestParticipant.contest_id)
            .all()
        )
        participant_counts = {contest_id: int(count or 0) for contest_id, count in rows}

    return render_template(
        'contests/list.html',
        contests=paginated.items,
        paginated=paginated,
        q=q,
        participant_counts=participant_counts,
    )


@web_bp.route('/contest/<int:contest_id>')
def contest_detail(contest_id):
    contest = Contest.query.get_or_404(contest_id)
    if not contest.is_public:
        abort(403)

    participant = None
    if current_user.is_authenticated:
        participant = ContestParticipant.query.filter_by(
            contest_id=contest.id,
            user_id=current_user.id,
        ).first()

    has_password = bool(contest.password)
    password_key = f'contest_pw_{contest.id}'
    password_ok = session.get(password_key, False) or bool(participant)

    problem_stats = []
    problem_status = {}
    if participant:
        problem_status = contest.get_problem_status(current_user.id)

    contest_problem_list = contest.problem_list
    problem_ids = [cp.problem_id for cp in contest_problem_list]
    problem_aggregate = {}

    if problem_ids:
        aggregate_rows = (
            db.session.query(
                Submission.problem_id.label('problem_id'),
                db.func.count(db.distinct(Submission.user_id)).label('submitted_count'),
                db.func.count(
                    db.distinct(
                        case(
                            (Submission.status == 'AC', Submission.user_id),
                            else_=None,
                        )
                    )
                ).label('accepted_count'),
            )
            .filter(
                Submission.contest_id == contest.id,
                Submission.problem_id.in_(problem_ids),
            )
            .group_by(
                Submission.problem_id,
            )
            .all()
        )

        problem_aggregate = {
            row.problem_id: {
                'submitted_count': int(row.submitted_count or 0),
                'accepted_count': int(row.accepted_count or 0),
            }
            for row in aggregate_rows
        }

    for cp in contest_problem_list:
        counts = problem_aggregate.get(cp.problem_id, {})
        user_state = problem_status.get(cp.id, {})
        problem_stats.append(
            {
                'contest_problem': cp,
                'submitted_count': counts.get('submitted_count', 0),
                'accepted_count': counts.get('accepted_count', 0),
                'user_status': user_state.get('status'),
                'user_attempts': user_state.get('attempts', 0),
            }
        )

    now = datetime.utcnow()
    remaining = ''
    if contest.status == 'Running':
        remaining = _format_remaining(contest.end_time - now)
    elif contest.status == 'Pending':
        remaining = _format_remaining(contest.start_time - now)

    return render_template(
        'contests/detail.html',
        contest=contest,
        participant=participant,
        has_password=has_password,
        password_ok=password_ok,
        problem_stats=problem_stats,
        remaining=remaining,
    )


@web_bp.route('/contest/<int:contest_id>/register', methods=['POST'])
@login_required
def contest_register(contest_id):
    contest = Contest.query.get_or_404(contest_id)
    if not contest.is_public:
        abort(403)

    existing = ContestParticipant.query.filter_by(
        contest_id=contest.id,
        user_id=current_user.id,
    ).first()
    if existing:
        flash(t('flash.already_registered'), 'error')
        return redirect(url_for('web.contest_detail', contest_id=contest.id))

    if not contest.is_registration_open:
        flash(t('flash.registration_closed'), 'error')
        return redirect(url_for('web.contest_detail', contest_id=contest.id))

    if contest.password:
        pwd = request.form.get('password', '').strip()
        if not _contest_password_matches(contest, pwd):
            flash(t('flash.invalid_contest_password'), 'error')
            return redirect(url_for('web.contest_detail', contest_id=contest.id))
        session[f'contest_pw_{contest.id}'] = True

    participant = ContestParticipant(contest_id=contest.id, user_id=current_user.id)
    db.session.add(participant)
    try:
        db.session.commit()
    except IntegrityError:
        # The unique (contest_id, user_id) key means a concurrent duplicate lost.
        db.session.rollback()
        flash(t('flash.already_registered'), 'error')
        return redirect(url_for('web.contest_detail', contest_id=contest.id))

    # The cap check above is a read, so two concurrent registrations could both
    # pass it and overshoot max_participants. SQLite has no row locking, so admit
    # the row first and withdraw it if this request is the one that went over.
    if contest.max_participants:
        placed = (
            db.session.query(db.func.count(ContestParticipant.id))
            .filter(
                ContestParticipant.contest_id == contest.id,
                ContestParticipant.is_disqualified.is_(False),
                ContestParticipant.id <= participant.id,
            )
            .scalar()
            or 0
        )
        if placed > contest.max_participants:
            db.session.delete(participant)
            db.session.commit()
            flash(t('flash.registration_closed'), 'error')
            return redirect(url_for('web.contest_detail', contest_id=contest.id))

    flash(t('flash.registration_success_short'), 'success')
    return redirect(url_for('web.contest_detail', contest_id=contest.id))


@web_bp.route('/contest/<int:contest_id>/problem/<alias>')
@login_required
def contest_problem_detail(contest_id, alias):
    contest = Contest.query.get_or_404(contest_id)
    participant = ContestParticipant.query.filter_by(
        contest_id=contest.id,
        user_id=current_user.id,
    ).first()
    if not participant or participant.is_disqualified:
        abort(403)

    if contest.status == 'Pending':
        flash(t('flash.contest_not_started'), 'error')
        return redirect(url_for('web.contest_detail', contest_id=contest.id))

    cp = _resolve_contest_problem(contest, alias)
    if not cp:
        abort(404)
    problem = Problem.query.get_or_404(cp.problem_id)

    supported_languages = current_app.config['SUPPORTED_LANGUAGES']
    submission_idempotency_key = secrets.token_urlsafe(32)

    return render_template(
        'contests/problem_detail.html',
        contest=contest,
        contest_problem=cp,
        problem=problem,
        supported_languages=supported_languages,
        submission_idempotency_key=submission_idempotency_key,
    )


@web_bp.route('/contest/<int:contest_id>/submit/<alias>', methods=['POST'])
@login_required
def contest_submit(contest_id, alias):
    contest = Contest.query.get_or_404(contest_id)
    participant = ContestParticipant.query.filter_by(
        contest_id=contest.id,
        user_id=current_user.id,
    ).first()
    if not participant or participant.is_disqualified:
        abort(403)

    if contest.status != 'Running':
        flash(t('flash.contest_not_running'), 'error')
        return redirect(url_for('web.contest_detail', contest_id=contest.id))

    cp = _resolve_contest_problem(contest, alias)
    if not cp:
        abort(404)

    supported_languages = current_app.config['SUPPORTED_LANGUAGES']
    language = request.form.get('language', '')
    code = request.form.get('code', '')
    if language not in supported_languages:
        flash(t('flash.unsupported_language'), 'error')
        return redirect(url_for('web.contest_problem_detail', contest_id=contest.id, alias=alias))
    if not code:
        flash(t('flash.code_empty'), 'error')
        return redirect(url_for('web.contest_problem_detail', contest_id=contest.id, alias=alias))
    if len(code) > 64 * 1024:
        flash(t('flash.code_limit'), 'error')
        return redirect(url_for('web.contest_problem_detail', contest_id=contest.id, alias=alias))

    try:
        sanitize_code(code, language)
    except DangerousCodeError as exc:
        flash(t('flash.code_feature_blocked', feature=exc.feature), 'error')
        return redirect(url_for('web.contest_problem_detail', contest_id=contest.id, alias=alias))
    except ValueError:
        flash(t('flash.code_limit'), 'error')
        return redirect(url_for('web.contest_problem_detail', contest_id=contest.id, alias=alias))

    raw_token = _submission_client_token()
    if raw_token and len(raw_token) > 512:
        flash(t('flash.invalid_request'), 'error')
        return redirect(url_for('web.contest_problem_detail', contest_id=contest.id, alias=alias))
    client_token = _scoped_client_token(raw_token, language, code)

    if client_token:
        existing = Submission.query.filter_by(
            user_id=current_user.id,
            problem_id=cp.problem_id,
            contest_id=contest.id,
            client_token=client_token,
        ).first()
        if existing:
            # Same token AND same code: a double submit, not a new attempt. Say so
            # instead of silently showing the previous verdict.
            flash(t('flash.duplicate_submission'), 'warning')
            return redirect(url_for('web.submission_detail', submission_id=existing.id))

    if not submission_allowed():
        flash(t('flash.too_many_submissions'), 'error')
        return redirect(url_for('web.contest_problem_detail', contest_id=contest.id, alias=alias))

    submission = Submission(
        user_id=current_user.id,
        problem_id=cp.problem_id,
        contest_id=contest.id,
        language=language,
        code=code,
        status='Pending',
        client_token=client_token,
    )
    db.session.add(submission)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # Another request won the unique-key race; make the retry idempotent.
        if client_token:
            existing = Submission.query.filter_by(
                user_id=current_user.id,
                problem_id=cp.problem_id,
                contest_id=contest.id,
                client_token=client_token,
            ).first()
            if existing:
                flash(t('flash.duplicate_submission'), 'warning')
                return redirect(url_for('web.submission_detail', submission_id=existing.id))
        raise

    if enqueue_submission(submission):
        flash(t('flash.submission_received'), 'success')
    else:
        flash(t('flash.judge_unavailable'), 'error')

    # Same destination as a practice submission: the detail page tracks judging
    # live, whereas the contest list needed a manual refresh to show a verdict.
    return redirect(url_for('web.submission_detail', submission_id=submission.id))


@web_bp.route('/contest/<int:contest_id>/submissions')
@login_required
def contest_submissions(contest_id):
    contest = Contest.query.get_or_404(contest_id)
    participant = ContestParticipant.query.filter_by(
        contest_id=contest.id,
        user_id=current_user.id,
    ).first()
    if not participant or participant.is_disqualified:
        abort(403)

    page = request.args.get('page', 1, type=int)
    # Source is not rendered here, and code can be 64 KB per row.
    query = (
        Submission.query.filter_by(
            contest_id=contest.id,
            user_id=current_user.id,
        )
        .options(defer(Submission.code))
        .order_by(Submission.submitted_at.desc())
    )
    paginated = query.paginate(page=page, per_page=20, error_out=False)

    alias_map = {cp.problem_id: cp.display_alias for cp in contest.problem_list}

    return render_template(
        'contests/submissions.html',
        contest=contest,
        submissions=paginated.items,
        pagination=paginated,
        alias_map=alias_map,
    )


@web_bp.route('/contest/<int:contest_id>/ranklist')
def contest_ranklist(contest_id):
    contest = Contest.query.get_or_404(contest_id)
    if not contest.is_public:
        abort(403)

    admin_view = current_user.is_authenticated and current_user.is_admin
    ranklist_hidden = contest.is_sealed and contest.status != 'Ended' and not admin_view
    ranklist = [] if ranklist_hidden else contest.get_ranklist()

    return render_template(
        'contests/ranklist.html',
        contest=contest,
        ranklist=ranklist,
        ranklist_hidden=ranklist_hidden,
    )
