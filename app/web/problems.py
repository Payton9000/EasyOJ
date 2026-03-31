import os

from flask import (render_template, request, redirect, url_for, flash,
                   current_app, abort)
from flask_login import login_required, current_user

from app import db
from app.models.problem import Problem
from app.models.submission import Submission
from app.utils.file_utils import ensure_dir, get_submission_dir
from app.web import web_bp


@web_bp.route('/')
def index():
    return redirect(url_for('web.problem_list'))


@web_bp.route('/problems')
def problem_list():
    page = request.args.get('page', 1, type=int)
    difficulty = request.args.get('difficulty', '')
    q = request.args.get('q', '')

    query = Problem.query.filter_by(is_public=True)
    if difficulty in ('easy', 'medium', 'hard'):
        query = query.filter_by(difficulty=difficulty)
    if q:
        query = query.filter(Problem.title.ilike(f'%{q}%'))

    pagination = query.paginate(page=page, per_page=20, error_out=False)
    return render_template('problems/list.html', problems=pagination.items,
                           pagination=pagination, difficulty=difficulty, q=q)


@web_bp.route('/problem/<int:problem_id>')
def problem_detail(problem_id):
    problem = Problem.query.get_or_404(problem_id)
    if not problem.is_public and (not current_user.is_authenticated or not current_user.is_admin):
        abort(403)
    return render_template('problems/detail.html', problem=problem)


@web_bp.route('/problem/<int:problem_id>/submit', methods=['GET', 'POST'])
@login_required
def problem_submit(problem_id):
    problem = Problem.query.get_or_404(problem_id)
    supported_languages = current_app.config['SUPPORTED_LANGUAGES']

    if request.method == 'POST':
        language = request.form.get('language', '')
        code = request.form.get('code', '')

        if language not in supported_languages:
            flash('Unsupported language.', 'error')
            return redirect(url_for('web.problem_submit', problem_id=problem_id))
        if not code:
            flash('Code cannot be empty.', 'error')
            return redirect(url_for('web.problem_submit', problem_id=problem_id))
        if len(code) > 64 * 1024:
            flash('Code exceeds 64KB limit.', 'error')
            return redirect(url_for('web.problem_submit', problem_id=problem_id))

        submission = Submission(
            user_id=current_user.id,
            problem_id=problem_id,
            language=language,
            code=code,
            status='Pending',
        )
        db.session.add(submission)
        db.session.commit()

        # Save code to submissions directory
        sub_dir = get_submission_dir(submission.id)
        ensure_dir(sub_dir)

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

        return redirect(url_for('web.submission_detail', submission_id=submission.id))

    return render_template('problems/submit.html', problem=problem,
                           supported_languages=supported_languages)


@web_bp.route('/submission/<int:submission_id>')
@login_required
def submission_detail(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    if submission.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    problem = Problem.query.get(submission.problem_id)
    return render_template('submissions/detail.html', submission=submission, problem=problem)


@web_bp.route('/submissions')
@login_required
def submission_list():
    page = request.args.get('page', 1, type=int)
    query = Submission.query.filter_by(user_id=current_user.id).order_by(
        Submission.submitted_at.desc())
    pagination = query.paginate(page=page, per_page=20, error_out=False)
    return render_template('submissions/list.html', submissions=pagination.items,
                           pagination=pagination)
