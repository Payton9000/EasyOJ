import os
import shutil

from flask import (render_template, request, redirect, url_for, flash,
                   current_app, abort)
from flask_login import login_required, current_user

from app import db
from app.models.problem import Problem
from app.models.submission import Submission
from app.models.user import User
from app.utils.file_utils import ensure_dir, get_problem_dir
from app.web import web_bp


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@web_bp.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    user_count = User.query.count()
    problem_count = Problem.query.count()
    submission_count = Submission.query.count()
    ac_count = Submission.query.filter_by(status='AC').count()
    recent_submissions = Submission.query.order_by(Submission.submitted_at.desc()).limit(10).all()
    return render_template('admin/dashboard.html',
                           user_count=user_count,
                           problem_count=problem_count,
                           submission_count=submission_count,
                           ac_count=ac_count,
                           recent_submissions=recent_submissions)


@web_bp.route('/admin/problems')
@login_required
@admin_required
def admin_problems():
    page = request.args.get('page', 1, type=int)
    pagination = Problem.query.paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/problems.html', problems=pagination.items, pagination=pagination)


@web_bp.route('/admin/problem/create', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_problem_create():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        if not title or not description:
            flash('Title and description are required.', 'error')
            return redirect(url_for('web.admin_problem_create'))

        time_limit = int(request.form.get('time_limit', 1000))
        time_limit = max(100, min(30000, time_limit))
        memory_limit = int(request.form.get('memory_limit', 256))
        memory_limit = max(16, min(1024, memory_limit))

        problem = Problem(
            title=title,
            description=description,
            input_description=request.form.get('input_description', ''),
            output_description=request.form.get('output_description', ''),
            sample_input=request.form.get('sample_input', ''),
            sample_output=request.form.get('sample_output', ''),
            time_limit=time_limit,
            memory_limit=memory_limit,
            difficulty=request.form.get('difficulty', 'medium'),
            source=request.form.get('source', ''),
            is_public=bool(request.form.get('is_public')),
            created_by=current_user.id,
        )
        db.session.add(problem)
        db.session.commit()

        tc_dir = os.path.join(get_problem_dir(problem.id), 'testcases')
        ensure_dir(tc_dir)

        flash('Problem created successfully.', 'success')
        return redirect(url_for('web.admin_problem_edit', problem_id=problem.id))

    return render_template('admin/problem_form.html', problem=None)


@web_bp.route('/admin/problem/<int:problem_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_problem_edit(problem_id):
    problem = Problem.query.get_or_404(problem_id)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        if not title or not description:
            flash('Title and description are required.', 'error')
            return redirect(url_for('web.admin_problem_edit', problem_id=problem_id))

        problem.title = title
        problem.description = description
        problem.input_description = request.form.get('input_description', '')
        problem.output_description = request.form.get('output_description', '')
        problem.sample_input = request.form.get('sample_input', '')
        problem.sample_output = request.form.get('sample_output', '')
        problem.time_limit = max(100, min(30000, int(request.form.get('time_limit', 1000))))
        problem.memory_limit = max(16, min(1024, int(request.form.get('memory_limit', 256))))
        problem.difficulty = request.form.get('difficulty', 'medium')
        problem.source = request.form.get('source', '')
        problem.is_public = bool(request.form.get('is_public'))
        db.session.commit()
        flash('Problem updated successfully.', 'success')
        return redirect(url_for('web.admin_problem_edit', problem_id=problem_id))

    return render_template('admin/problem_form.html', problem=problem)


@web_bp.route('/admin/problem/<int:problem_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_problem_delete(problem_id):
    problem = Problem.query.get_or_404(problem_id)
    db.session.delete(problem)
    db.session.commit()
    problem_dir = get_problem_dir(problem_id)
    if os.path.isdir(problem_dir):
        shutil.rmtree(problem_dir, ignore_errors=True)
    flash('Problem deleted.', 'success')
    return redirect(url_for('web.admin_problems'))


@web_bp.route('/admin/problem/<int:problem_id>/upload_testcase', methods=['POST'])
@login_required
@admin_required
def admin_upload_testcase(problem_id):
    problem = Problem.query.get_or_404(problem_id)
    input_file = request.files.get('input_file')
    output_file = request.files.get('output_file')
    if not input_file or not output_file:
        flash('Both input and output files are required.', 'error')
        return redirect(url_for('web.admin_problem_edit', problem_id=problem_id))

    tc_dir = os.path.join(get_problem_dir(problem_id), 'testcases')
    ensure_dir(tc_dir)

    existing = [f for f in os.listdir(tc_dir) if f.endswith('.in')]
    next_num = len(existing) + 1

    input_file.save(os.path.join(tc_dir, f'{next_num}.in'))
    output_file.save(os.path.join(tc_dir, f'{next_num}.out'))

    flash(f'Test case {next_num} uploaded.', 'success')
    return redirect(url_for('web.admin_problem_edit', problem_id=problem_id))


@web_bp.route('/admin/users')
@login_required
@admin_required
def admin_users():
    page = request.args.get('page', 1, type=int)
    pagination = User.query.paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/users.html', users=pagination.items, pagination=pagination)


@web_bp.route('/admin/user/<int:user_id>/toggle_active', methods=['POST'])
@login_required
@admin_required
def admin_toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    state = 'activated' if user.is_active else 'deactivated'
    flash(f'User {user.username} {state}.', 'success')
    return redirect(url_for('web.admin_users'))
