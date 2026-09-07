import json
import os
import re
from difflib import SequenceMatcher

from flask import abort
from flask import current_app
from flask import flash
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask_login import current_user
from flask_login import login_required
from sqlalchemy.orm import defer

from app import db
from app.i18n import translate as t
from app.models.judge_task import JudgeTask
from app.models.problem import Problem
from app.models.submission import Submission
from app.services.submission_service import enqueue_submission
from app.services.submission_service import find_active_contest_problem
from app.services.submission_service import problem_in_running_contest
from app.services.submission_service import submission_is_in_active_contest
from app.utils.file_utils import ensure_dir
from app.utils.file_utils import get_submission_dir
from app.utils.rate_limit import submission_allowed
from app.utils.security import DangerousCodeError
from app.utils.security import sanitize_code
from app.web import web_bp


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_submission_judge_log(submission_id):
    task = JudgeTask.query.filter_by(submission_id=submission_id).first()
    log_path = None

    if task and task.debug_log_path and os.path.isfile(task.debug_log_path):
        log_path = task.debug_log_path
    else:
        log_dir = current_app.config.get('JUDGE_LOG_DIR')
        if log_dir:
            fallback = os.path.join(log_dir, f'submission_{submission_id}.json')
            if os.path.isfile(fallback):
                log_path = fallback

    if not log_path:
        return None

    try:
        with open(log_path, encoding='utf-8') as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None


def _normalize_case_logs(case_logs):
    normalized = []
    max_time = 0
    max_memory = 0

    for idx, item in enumerate(case_logs or [], start=1):
        if not isinstance(item, dict):
            continue

        time_ms = max(0, _safe_int(item.get('time_ms'), 0))
        memory_kb = max(0, _safe_int(item.get('memory_kb'), 0))
        max_time = max(max_time, time_ms)
        max_memory = max(max_memory, memory_kb)

        raw_status = str(item.get('status') or 'UNKNOWN').upper()
        normalized.append(
            {
                'case': _safe_int(item.get('case'), idx),
                'raw_status': raw_status,
                'status': 'AC' if raw_status == 'OK' else raw_status,
                'time_ms': time_ms,
                'memory_kb': memory_kb,
                'memory_mb': round(memory_kb / 1024, 2) if memory_kb else 0,
                'error': (item.get('error') or '').strip(),
                'output_sample': item.get('output_sample') or '',
                'expected_sample': item.get('expected_sample') or '',
            }
        )

    for item in normalized:
        item['time_pct'] = int(item['time_ms'] / max_time * 100) if max_time else 0
        item['memory_pct'] = int(item['memory_kb'] / max_memory * 100) if max_memory else 0

    return normalized


def _parse_compile_errors(error_message):
    if not error_message:
        return []

    patterns = [
        re.compile(
            r'^(?P<file>[^:\s][^:]*):(?P<line>\d+):(?P<column>\d+):\s*'
            r'(?P<level>fatal error|error|warning|note):\s*(?P<message>.+)$',
            re.IGNORECASE,
        ),
        re.compile(
            r'^(?P<file>[^:\s][^:]*):(?P<line>\d+):\s*'
            r'(?P<level>error|warning):\s*(?P<message>.+)$',
            re.IGNORECASE,
        ),
    ]

    entries = []
    for raw_line in error_message.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = None
        for pattern in patterns:
            matched = pattern.match(line)
            if matched:
                match = matched
                break

        if match:
            groups = match.groupdict()
            entries.append(
                {
                    'file': groups.get('file') or '',
                    'line': _safe_int(groups.get('line'), 0),
                    'column': _safe_int(groups.get('column'), 0),
                    'level': (groups.get('level') or 'error').lower(),
                    'message': (groups.get('message') or '').strip(),
                    'raw': line,
                }
            )

    return entries[:100]


def _build_diff_rows(expected_sample, output_sample, max_rows=40):
    expected_lines = (expected_sample or '').splitlines()
    output_lines = (output_sample or '').splitlines()
    matcher = SequenceMatcher(None, expected_lines, output_lines)

    rows = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if len(rows) >= max_rows:
            break

        if tag == 'equal':
            if i2 - i1 > 1:
                rows.append({'kind': 'same', 'expected': '...', 'actual': '...'})
            elif i2 > i1:
                rows.append(
                    {
                        'kind': 'same',
                        'expected': expected_lines[i1],
                        'actual': output_lines[j1],
                    }
                )
            continue

        width = max(i2 - i1, j2 - j1)
        for offset in range(width):
            if len(rows) >= max_rows:
                break
            expected_line = expected_lines[i1 + offset] if i1 + offset < i2 else ''
            output_line = output_lines[j1 + offset] if j1 + offset < j2 else ''
            rows.append(
                {
                    'kind': tag,
                    'expected': expected_line,
                    'actual': output_line,
                }
            )

    if not rows:
        rows.append({'kind': 'same', 'expected': '(empty)', 'actual': '(empty)'})
    elif len(rows) >= max_rows:
        rows.append({'kind': 'truncated', 'expected': '...', 'actual': '...'})

    return rows


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

    # Without an explicit order SQLite may return rows in any order, so a problem
    # could move between pages (or vanish from page 1) across requests.
    pagination = query.order_by(Problem.id.asc()).paginate(page=page, per_page=20, error_out=False)
    return render_template(
        'problems/list.html',
        problems=pagination.items,
        pagination=pagination,
        difficulty=difficulty,
        q=q,
    )


@web_bp.route('/problem/<int:problem_id>')
def problem_detail(problem_id):
    problem = Problem.query.get_or_404(problem_id)
    if not problem.is_public and (not current_user.is_authenticated or not current_user.is_admin):
        abort(404)
    return render_template('problems/detail.html', problem=problem)


@web_bp.route('/problem/<int:problem_id>/submit', methods=['GET', 'POST'])
@login_required
def problem_submit(problem_id):
    problem = Problem.query.get_or_404(problem_id)
    if not problem.is_public and not current_user.is_admin:
        abort(404)

    if problem.is_public:
        active_contest_problem = find_active_contest_problem(problem_id, current_user.id)
        if active_contest_problem:
            flash(
                t('flash.active_contest_problem'),
                'warning',
            )
            return redirect(
                url_for(
                    'web.contest_problem_detail',
                    contest_id=active_contest_problem.contest_id,
                    alias=active_contest_problem.alias,
                )
            )
        # Non-participants must not reach the practice path either: the judge
        # report would expose expected output for a problem still being contested.
        if problem_in_running_contest(problem_id):
            flash(t('flash.problem_locked_by_contest'), 'warning')
            return redirect(url_for('web.problem_detail', problem_id=problem_id))

    supported_languages = current_app.config['SUPPORTED_LANGUAGES']

    if request.method == 'POST':
        language = request.form.get('language', '')
        code = request.form.get('code', '')

        if language not in supported_languages:
            flash(t('flash.unsupported_language'), 'error')
            return render_template(
                'problems/submit.html',
                problem=problem,
                supported_languages=supported_languages,
                code=code,
                language=language,
            )
        if not code:
            flash(t('flash.code_empty'), 'error')
            return render_template(
                'problems/submit.html',
                problem=problem,
                supported_languages=supported_languages,
                code=code,
                language=language,
            )
        if len(code) > 64 * 1024:
            flash(t('flash.code_limit'), 'error')
            return render_template(
                'problems/submit.html',
                problem=problem,
                supported_languages=supported_languages,
                code=code,
                language=language,
            )

        try:
            sanitize_code(code, language)
        except DangerousCodeError as exc:
            flash(t('flash.code_feature_blocked', feature=exc.feature), 'error')
            return render_template(
                'problems/submit.html',
                problem=problem,
                supported_languages=supported_languages,
                code=code,
                language=language,
            )

        if not submission_allowed():
            flash(t('flash.too_many_submissions'), 'error')
            return render_template(
                'problems/submit.html',
                problem=problem,
                supported_languages=supported_languages,
                code=code,
                language=language,
            )

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

        if enqueue_submission(submission):
            flash(t('flash.submission_received'), 'success')
        else:
            flash(t('flash.judge_unavailable'), 'error')

        return redirect(url_for('web.submission_detail', submission_id=submission.id))

    return render_template(
        'problems/submit.html', problem=problem, supported_languages=supported_languages
    )


@web_bp.route('/submission/<int:submission_id>')
@login_required
def submission_detail(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    if submission.user_id != current_user.id and not current_user.is_admin:
        abort(403)

    judge_log = _load_submission_judge_log(submission.id)
    case_details = _normalize_case_logs((judge_log or {}).get('cases', []))
    failed_case = next(
        (item for item in case_details if item.get('raw_status') not in ('OK', 'AC')),
        None,
    )

    contest_is_running = submission_is_in_active_contest(submission)

    diff_rows = []
    if failed_case and not contest_is_running:
        expected = failed_case.get('expected_sample', '')
        output = failed_case.get('output_sample', '')
        if expected or output:
            diff_rows = _build_diff_rows(expected, output)
        failed_case['expected_sample'] = expected
    elif failed_case and contest_is_running:
        failed_case['expected_sample'] = ''

    compile_error_entries = []
    if submission.status == 'CE':
        compile_error_entries = _parse_compile_errors(submission.error_message)

    problem = db.session.get(Problem, submission.problem_id)
    return render_template(
        'submissions/detail.html',
        submission=submission,
        problem=problem,
        case_details=case_details,
        failed_case=failed_case,
        diff_rows=diff_rows,
        compile_error_entries=compile_error_entries,
    )


@web_bp.route('/submissions')
@login_required
def submission_list():
    page = request.args.get('page', 1, type=int)
    # The list never shows source, but code can be 64 KB per row.
    query = (
        Submission.query.filter_by(user_id=current_user.id)
        .options(defer(Submission.code))
        .order_by(Submission.submitted_at.desc())
    )
    pagination = query.paginate(page=page, per_page=20, error_out=False)
    return render_template(
        'submissions/list.html', submissions=pagination.items, pagination=pagination
    )
