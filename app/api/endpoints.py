from flask import current_app
from flask import jsonify
from flask import request
from flask_login import current_user
from flask_wtf.csrf import generate_csrf
from werkzeug.exceptions import RequestEntityTooLarge

from app import db
from app.api import api_bp
from app.api import api_login_required
from app.models.problem import Problem
from app.models.submission import Submission
from app.services.submission_service import enqueue_submission
from app.services.submission_service import find_active_contest_problem
from app.services.submission_service import problem_in_running_contest
from app.utils.file_utils import ensure_dir
from app.utils.file_utils import get_submission_dir
from app.utils.pagination import parse_pagination
from app.utils.rate_limit import submission_allowed
from app.utils.security import DangerousCodeError
from app.utils.security import sanitize_code


def _practice_service():
    from app.judge.practice import PracticeRunService

    service = current_app.extensions.get('easyoj_practice_service')
    if service is None:
        service = PracticeRunService(current_app._get_current_object())
        current_app.extensions['easyoj_practice_service'] = service
    return service


def _fmt(dt):
    return dt.isoformat() if dt else None


def _api_internal_error(operation, exc):
    current_app.logger.exception('API operation failed: %s', operation, exc_info=exc)
    return jsonify({'code': 500, 'message': 'Internal server error'}), 500


@api_bp.route('/csrf-token')
@api_login_required
def api_csrf_token():
    return jsonify({'code': 0, 'data': {'csrf_token': generate_csrf()}})


@api_bp.route('/problems')
def api_problems():
    try:
        page, per_page = parse_pagination(request.args)
        difficulty = request.args.get('difficulty', '')
        q = request.args.get('q', '')

        query = Problem.query.filter_by(is_public=True)
        if difficulty in ('easy', 'medium', 'hard'):
            query = query.filter_by(difficulty=difficulty)
        if q:
            query = query.filter(Problem.title.ilike(f'%{q}%'))

        # Deterministic order: unordered pagination can shuffle rows between pages.
        pagination = query.order_by(Problem.id.asc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        data = [
            {
                'id': p.id,
                'title': p.title,
                'difficulty': p.difficulty,
                'time_limit': p.time_limit,
                'memory_limit': p.memory_limit,
                'source': p.source,
            }
            for p in pagination.items
        ]

        return jsonify(
            {
                'code': 0,
                'data': {
                    'problems': data,
                    'total': pagination.total,
                    'page': page,
                    'per_page': per_page,
                    'pages': pagination.pages,
                },
            }
        )
    except Exception as exc:
        return _api_internal_error('list problems', exc)


@api_bp.route('/problems/<int:problem_id>')
def api_problem_detail(problem_id):
    try:
        problem = db.session.get(Problem, problem_id)
        if not problem or (
            not problem.is_public
            and (not current_user.is_authenticated or not current_user.is_admin)
        ):
            return jsonify({'code': 404, 'message': 'Problem not found'}), 404
        return jsonify(
            {
                'code': 0,
                'data': {
                    'id': problem.id,
                    'title': problem.title,
                    'description': problem.description,
                    'input_description': problem.input_description,
                    'output_description': problem.output_description,
                    'sample_input': problem.sample_input,
                    'sample_output': problem.sample_output,
                    'time_limit': problem.time_limit,
                    'memory_limit': problem.memory_limit,
                    'difficulty': problem.difficulty,
                    'source': problem.source,
                },
            }
        )
    except Exception as exc:
        return _api_internal_error('read problem', exc)


@api_bp.route('/submit/<int:problem_id>', methods=['POST'])
@api_login_required
def api_submit(problem_id):
    try:
        problem = db.session.get(Problem, problem_id)
        if not problem:
            return jsonify({'code': 404, 'message': 'Problem not found'}), 404
        if not problem.is_public and not current_user.is_admin:
            return jsonify({'code': 404, 'message': 'Problem not found'}), 404

        active_contest_problem = find_active_contest_problem(problem_id, current_user.id)
        if active_contest_problem:
            return jsonify(
                {
                    'code': 409,
                    'message': 'Submit this problem through its active contest',
                    'data': {
                        'contest_id': active_contest_problem.contest_id,
                        'alias': active_contest_problem.alias,
                    },
                }
            ), 409
        # Non-participants must not reach the practice path either: the judge
        # report would expose expected output for a problem still being contested.
        if problem_in_running_contest(problem_id):
            return jsonify(
                {
                    'code': 409,
                    'message': 'This problem is locked while a contest using it is running',
                }
            ), 409

        data = request.get_json(silent=True)
        if data is None:
            data = {}
        elif not isinstance(data, dict):
            return jsonify({'code': 400, 'message': 'JSON body must be an object'}), 400

        language = data.get('language', '')
        code = data.get('code', '')
        if not isinstance(language, str) or not isinstance(code, str):
            return jsonify({'code': 400, 'message': 'Language and code must be strings'}), 400

        supported = current_app.config['SUPPORTED_LANGUAGES']
        if language not in supported:
            return jsonify({'code': 400, 'message': 'Unsupported language'}), 400
        if not code:
            return jsonify({'code': 400, 'message': 'Code is required'}), 400
        if len(code) > 64 * 1024:
            return jsonify({'code': 400, 'message': 'Code exceeds 64KB limit'}), 400

        try:
            sanitize_code(code, language)
        except DangerousCodeError as exc:
            return jsonify(
                {
                    'code': 400,
                    'message': f'Code uses a feature that is not allowed here: {exc.feature}',
                }
            ), 400
        except ValueError:
            return jsonify({'code': 400, 'message': 'Code exceeds 64KB limit'}), 400

        if not submission_allowed():
            response = jsonify(
                {
                    'code': 429,
                    'message': 'Too many submissions. Please wait before trying again.',
                }
            )
            response.headers['Retry-After'] = str(
                current_app.config.get('SUBMISSION_RATE_WINDOW_SECONDS', 60)
            )
            return response, 429

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

        success = enqueue_submission(submission)
        if not success:
            return jsonify(
                {
                    'code': 503,
                    'message': 'Judge queue is full or unavailable',
                    'data': {'submission_id': submission.id},
                }
            ), 503

        return jsonify({'code': 0, 'data': {'submission_id': submission.id}})
    except RequestEntityTooLarge:
        return jsonify({'code': 413, 'message': 'Request payload is too large'}), 413
    except Exception as exc:
        return _api_internal_error('submit solution', exc)


@api_bp.route('/run/<int:problem_id>', methods=['POST'])
@api_login_required
def api_practice_run(problem_id):
    try:
        problem = db.session.get(Problem, problem_id)
        if not problem or (not problem.is_public and not current_user.is_admin):
            return jsonify({'code': 404, 'message': 'Problem not found'}), 404
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'code': 400, 'message': 'JSON body must be an object'}), 400
        result = _practice_service().run(
            problem,
            data.get('language', ''),
            data.get('code', ''),
            data.get('input', ''),
        )
        payload = {
            'status': result.status,
            'output': result.output,
            'error': result.error,
            'time_used': result.time_used,
            'memory_used': result.memory_used,
        }
        if result.status == 'Invalid':
            return jsonify({'code': 400, 'message': result.error, 'data': payload}), 400
        if result.status == 'Busy':
            response = jsonify({'code': 429, 'message': result.error, 'data': payload})
            response.headers['Retry-After'] = '2'
            return response, 429
        return jsonify({'code': 0, 'data': payload})
    except RequestEntityTooLarge:
        return jsonify({'code': 413, 'message': 'Request payload is too large'}), 413
    except Exception as exc:
        return _api_internal_error('run custom input', exc)


@api_bp.route('/submission/<int:submission_id>')
@api_login_required
def api_submission_detail(submission_id):
    try:
        submission = db.session.get(Submission, submission_id)
        if not submission:
            return jsonify({'code': 404, 'message': 'Submission not found'}), 404
        if submission.user_id != current_user.id and not current_user.is_admin:
            return jsonify({'code': 403, 'message': 'Forbidden'}), 403
        return jsonify(
            {
                'code': 0,
                'data': {
                    'id': submission.id,
                    'problem_id': submission.problem_id,
                    'language': submission.language,
                    'status': submission.status,
                    'time_used': submission.time_used,
                    'memory_used': submission.memory_used,
                    'test_case_passed': submission.test_case_passed,
                    'test_case_total': submission.test_case_total,
                    'error_message': submission.error_message,
                    'submitted_at': _fmt(submission.submitted_at),
                    'judged_at': _fmt(submission.judged_at),
                },
            }
        )
    except Exception as exc:
        return _api_internal_error('read submission', exc)


@api_bp.route('/submissions')
@api_login_required
def api_submissions():
    try:
        page, per_page = parse_pagination(request.args)
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
            page=page, per_page=per_page, error_out=False
        )
        data = [
            {
                'id': submission.id,
                'problem_id': submission.problem_id,
                'language': submission.language,
                'status': submission.status,
                'time_used': submission.time_used,
                'memory_used': submission.memory_used,
                'submitted_at': _fmt(submission.submitted_at),
            }
            for submission in pagination.items
        ]

        return jsonify(
            {
                'code': 0,
                'data': {
                    'submissions': data,
                    'total': pagination.total,
                    'page': page,
                    'per_page': per_page,
                    'pages': pagination.pages,
                },
            }
        )
    except Exception as exc:
        return _api_internal_error('list submissions', exc)


@api_bp.route('/ranking')
def api_ranking():
    try:
        from sqlalchemy import func

        from app.models.user import User

        rows = (
            db.session.query(
                User.id,
                User.username,
                func.count(Submission.id.distinct()).label('submit_count'),
                func.count(
                    db.case(
                        (Submission.status == 'AC', Submission.problem_id), else_=None
                    ).distinct()
                ).label('ac_count'),
            )
            .outerjoin(Submission, User.id == Submission.user_id)
            .group_by(User.id)
            .order_by(db.text('ac_count DESC'))
            .limit(50)
            .all()
        )

        ranking = []
        for rank, row in enumerate(rows, 1):
            ranking.append(
                {
                    'rank': rank,
                    'username': row.username,
                    'ac_count': row.ac_count,
                    'submit_count': row.submit_count,
                }
            )
        return jsonify({'code': 0, 'data': ranking})
    except Exception as exc:
        return _api_internal_error('read ranking', exc)
