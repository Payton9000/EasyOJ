from flask import render_template, request, abort, redirect, url_for, flash, session, current_app
from flask_login import current_user, login_required
from sqlalchemy import case

from app.web import web_bp
from app import db
from app.models.contest import Contest
from app.models.contest_problem import ContestProblem
from app.models.contest_participant import ContestParticipant
from app.models.problem import Problem
from app.models.submission import Submission


@web_bp.route('/contests')
def contest_list():
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str)

    query = Contest.query.filter(Contest.is_public == True)
    if q:
        query = query.filter(Contest.title.ilike(f'%{q}%'))

    query = query.order_by(Contest.start_time.desc())
    paginated = query.paginate(page=page, per_page=20, error_out=False)

    return render_template('contests/list.html',
                           contests=paginated.items,
                           paginated=paginated,
                           q=q)


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
        aggregate_rows = db.session.query(
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
        ).filter(
            Submission.contest_id == contest.id,
            Submission.problem_id.in_(problem_ids),
        ).group_by(
            Submission.problem_id,
        ).all()

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
        problem_stats.append({
            'contest_problem': cp,
            'submitted_count': counts.get('submitted_count', 0),
            'accepted_count': counts.get('accepted_count', 0),
            'user_status': user_state.get('status'),
            'user_attempts': user_state.get('attempts', 0),
        })

    return render_template(
        'contests/detail.html',
        contest=contest,
        participant=participant,
        has_password=has_password,
        password_ok=password_ok,
        problem_stats=problem_stats,
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
        flash('You are already registered.', 'error')
        return redirect(url_for('web.contest_detail', contest_id=contest.id))

    if not contest.is_registration_open:
        flash('Registration is closed.', 'error')
        return redirect(url_for('web.contest_detail', contest_id=contest.id))

    if contest.password:
        pwd = request.form.get('password', '').strip()
        if pwd != contest.password:
            flash('Invalid contest password.', 'error')
            return redirect(url_for('web.contest_detail', contest_id=contest.id))
        session[f'contest_pw_{contest.id}'] = True

    participant = ContestParticipant(contest_id=contest.id, user_id=current_user.id)
    db.session.add(participant)
    db.session.commit()

    flash('Registration successful.', 'success')
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
        flash('Contest has not started yet.', 'error')
        return redirect(url_for('web.contest_detail', contest_id=contest.id))

    cp = ContestProblem.query.filter_by(
        contest_id=contest.id,
        alias=alias.upper(),
    ).first()
    if not cp:
        abort(404)
    problem = Problem.query.get_or_404(cp.problem_id)

    supported_languages = current_app.config['SUPPORTED_LANGUAGES']

    return render_template(
        'contests/problem_detail.html',
        contest=contest,
        contest_problem=cp,
        problem=problem,
        supported_languages=supported_languages,
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
        flash('Contest is not running.', 'error')
        return redirect(url_for('web.contest_detail', contest_id=contest.id))

    cp = ContestProblem.query.filter_by(
        contest_id=contest.id,
        alias=alias.upper(),
    ).first()
    if not cp:
        abort(404)

    supported_languages = current_app.config['SUPPORTED_LANGUAGES']
    language = request.form.get('language', '')
    code = request.form.get('code', '')
    if language not in supported_languages:
        flash('Unsupported language.', 'error')
        return redirect(url_for('web.contest_problem_detail', contest_id=contest.id, alias=alias))
    if not code:
        flash('Code cannot be empty.', 'error')
        return redirect(url_for('web.contest_problem_detail', contest_id=contest.id, alias=alias))
    if len(code) > 64 * 1024:
        flash('Code exceeds 64KB limit.', 'error')
        return redirect(url_for('web.contest_problem_detail', contest_id=contest.id, alias=alias))

    submission = Submission(
        user_id=current_user.id,
        problem_id=cp.problem_id,
        contest_id=contest.id,
        language=language,
        code=code,
        status='Pending',
    )
    db.session.add(submission)
    db.session.commit()

    try:
        success = current_app.judge_engine.submit_judge_task(submission.id)
        if success:
            flash('Submission received! Judging in progress...', 'success')
        else:
            submission.status = 'Failed'
            db.session.commit()
            flash('Judge queue is full. Please try again later.', 'error')
    except Exception:
        flash('Failed to submit code for judging. Please try again.', 'error')

    return redirect(url_for('web.contest_submissions', contest_id=contest.id))


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
    query = Submission.query.filter_by(
        contest_id=contest.id,
        user_id=current_user.id,
    ).order_by(Submission.submitted_at.desc())
    paginated = query.paginate(page=page, per_page=20, error_out=False)

    alias_map = {cp.problem_id: cp.alias for cp in contest.problem_list}

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

    ranklist = contest.get_ranklist()

    return render_template(
        'contests/ranklist.html',
        contest=contest,
        ranklist=ranklist,
    )
