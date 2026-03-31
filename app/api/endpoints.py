from datetime import datetime

from flask import request, jsonify, current_app
from flask_login import current_user

from app import db
from app.api import api_bp, api_login_required
from app.models.problem import Problem
from app.models.submission import Submission
from app.utils.file_utils import ensure_dir, get_submission_dir


def _fmt(dt):
    return dt.isoformat() if dt else None


@api_bp.route('/problems')
def api_problems():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        difficulty = request.args.get('difficulty', '')
        q = request.args.get('q', '')

        query = Problem.query.filter_by(is_public=True)
        if difficulty in ('easy', 'medium', 'hard'):
            query = query.filter_by(difficulty=difficulty)
        if q:
            query = query.filter(Problem.title.ilike(f'%{q}%'))

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        data = [{
            'id': p.id, 'title': p.title, 'difficulty': p.difficulty,
            'time_limit': p.time_limit, 'memory_limit': p.memory_limit, 'source': p.source,
        } for p in pagination.items]

        return jsonify({'code': 0, 'data': {
            'problems': data,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages,
        }})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500


@api_bp.route('/problems/<int:problem_id>')
def api_problem_detail(problem_id):
    try:
        p = Problem.query.get(problem_id)
        if not p:
            return jsonify({'code': 404, 'message': 'Problem not found'}), 404
        return jsonify({'code': 0, 'data': {
            'id': p.id, 'title': p.title, 'description': p.description,
            'input_description': p.input_description, 'output_description': p.output_description,
            'sample_input': p.sample_input, 'sample_output': p.sample_output,
            'time_limit': p.time_limit, 'memory_limit': p.memory_limit,
            'difficulty': p.difficulty, 'source': p.source,
        }})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500


@api_bp.route('/submit/<int:problem_id>', methods=['POST'])
@api_login_required
def api_submit(problem_id):
    try:
        problem = Problem.query.get(problem_id)
        if not problem:
            return jsonify({'code': 404, 'message': 'Problem not found'}), 404

        data = request.get_json(silent=True) or {}
        language = data.get('language', '')
        code = data.get('code', '')

        supported = current_app.config['SUPPORTED_LANGUAGES']
        if language not in supported:
            return jsonify({'code': 400, 'message': 'Unsupported language'}), 400
        if not code:
            return jsonify({'code': 400, 'message': 'Code is required'}), 400
        if len(code) > 64 * 1024:
            return jsonify({'code': 400, 'message': 'Code exceeds 64KB limit'}), 400

        submission = Submission(
            user_id=current_user.id,
            problem_id=problem_id,
            language=language,
            code=code,
            status='Pending',
        )
        db.session.add(submission)
        db.session.commit()

        sub_dir = get_submission_dir(submission.id)
        ensure_dir(sub_dir)

        success = current_app.judge_engine.submit_judge_task(submission.id)
        if not success:
            return jsonify({'code': 503, 'message': 'Judge queue is full'}), 503

        return jsonify({'code': 0, 'data': {'submission_id': submission.id}})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500


@api_bp.route('/submission/<int:submission_id>')
@api_login_required
def api_submission_detail(submission_id):
    try:
        s = Submission.query.get(submission_id)
        if not s:
            return jsonify({'code': 404, 'message': 'Submission not found'}), 404
        if s.user_id != current_user.id and not current_user.is_admin:
            return jsonify({'code': 403, 'message': 'Forbidden'}), 403
        return jsonify({'code': 0, 'data': {
            'id': s.id, 'problem_id': s.problem_id, 'language': s.language,
            'status': s.status, 'time_used': s.time_used, 'memory_used': s.memory_used,
            'test_case_passed': s.test_case_passed, 'test_case_total': s.test_case_total,
            'error_message': s.error_message,
            'submitted_at': _fmt(s.submitted_at), 'judged_at': _fmt(s.judged_at),
        }})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500


@api_bp.route('/submissions')
@api_login_required
def api_submissions():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        problem_id = request.args.get('problem_id', type=int)
        status = request.args.get('status', '')
        user_id_param = request.args.get('user_id', type=int)

        if current_user.is_admin and user_id_param:
            query = Submission.query.filter_by(user_id=user_id_param)
        elif current_user.is_admin and not user_id_param:
            query = Submission.query
        else:
            query = Submission.query.filter_by(user_id=current_user.id)

        if problem_id:
            query = query.filter_by(problem_id=problem_id)
        if status:
            query = query.filter_by(status=status)

        pagination = query.order_by(Submission.submitted_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False)
        data = [{
            'id': s.id, 'problem_id': s.problem_id, 'language': s.language,
            'status': s.status, 'time_used': s.time_used, 'memory_used': s.memory_used,
            'submitted_at': _fmt(s.submitted_at),
        } for s in pagination.items]

        return jsonify({'code': 0, 'data': {
            'submissions': data,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages,
        }})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500


@api_bp.route('/ranking')
def api_ranking():
    try:
        from sqlalchemy import func
        from app.models.user import User

        rows = db.session.query(
            User.id, User.username,
            func.count(Submission.id.distinct()).label('submit_count'),
            func.count(
                db.case((Submission.status == 'AC', Submission.problem_id), else_=None).distinct()
            ).label('ac_count'),
        ).outerjoin(Submission, User.id == Submission.user_id) \
         .group_by(User.id) \
         .order_by(db.text('ac_count DESC')) \
         .limit(50).all()

        ranking = []
        for rank, row in enumerate(rows, 1):
            ranking.append({
                'rank': rank,
                'username': row.username,
                'ac_count': row.ac_count,
                'submit_count': row.submit_count,
            })
        return jsonify({'code': 0, 'data': ranking})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500
