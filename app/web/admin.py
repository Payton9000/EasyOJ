"""OJ系统管理后台模块

提供题目、竞赛、用户、提交记录等管理功能
"""

import os
import shutil
import tempfile
from datetime import datetime
from threading import Lock

from flask import Blueprint
from flask import current_app
from flask import flash as flask_flash
from flask import has_app_context
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from app import db
from app.i18n import translate as t
from app.models import Contest
from app.models import ContestParticipant
from app.models import ContestProblem
from app.models import JudgeTask
from app.models import Problem
from app.models import Submission
from app.models import User
from app.services.account_service import AccountService
from app.utils.decorators import admin_required
from app.utils.file_utils import TestcaseUploadError
from app.utils.file_utils import available_disk_bytes
from app.utils.file_utils import ensure_dir
from app.utils.file_utils import testcase_limits
from app.utils.file_utils import validate_testcase_directory
from app.utils.file_utils import validate_testcase_storage
from app.utils.file_utils import validate_testcase_upload
from app.utils.file_utils import validate_upload_filename
from app.utils.time_utils import parse_local_datetime_to_utc

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

_FLASH_KEYS = {
    '标题和描述不能为空': 'admin.title_required',
    '时间和内存限制必须为整数': 'admin.limits_integer',
    '题目创建成功': 'admin.create_success',
    '题目更新成功': 'admin.update_success',
    '删除确认失败：输入的标题不匹配': 'admin.delete_confirmation_failed',
    '题目删除成功': 'admin.delete_success',
    '测试用例上传成功': 'admin.upload_success',
    '上传失败，请检查文件后重试': 'admin.upload_failed',
    '测试用例删除成功': 'admin.testcase_deleted',
    '竞赛标题不能为空': 'admin.contest_title_required',
    '开始时间和结束时间格式错误': 'admin.datetime_invalid',
    '开始时间必须早于结束时间': 'admin.start_before_end',
    '开始时间不能早于当前时间': 'admin.start_not_past',
    '竞赛创建成功': 'admin.create_success',
    '竞赛更新成功': 'admin.update_success',
    '竞赛删除成功': 'admin.delete_success',
    '请选择题目': 'admin.select_problem',
    '该题目已在竞赛中': 'admin.problem_in_contest',
    '题目添加成功': 'admin.problem_added',
    '题目已移除': 'admin.problem_removed',
    '用户不存在': 'admin.user_not_found',
    '该用户已是参赛者': 'admin.user_already_participant',
    '参赛人数已达上限': 'admin.participant_limit',
    '参赛者添加成功': 'admin.participant_added',
    '参赛者已移除': 'admin.participant_removed',
    '不能修改自己的角色': 'admin.cannot_change_self_role',
    '已重新提交判题任务': 'admin.rejudge_success',
    'This account change would remove your access or the last active administrator.': 'admin.account_state_blocked',
}


def flash(message, category=None):
    key = _FLASH_KEYS.get(message)
    if key:
        message = t(key)
    elif isinstance(message, str) and message.startswith('题目已'):
        message = t('admin.item_status', status=message[3:])
    elif isinstance(message, str) and message.startswith('用户'):
        message = t('admin.user_status', status=message[2:])
    return flask_flash(message, category)


_TESTCASE_UPLOAD_LOCK = Lock()


def _save_upload_stream(upload, target_path, max_bytes, chunk_bytes):
    total = 0
    try:
        with open(target_path, 'wb') as target:
            while True:
                chunk = upload.stream.read(chunk_bytes)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise TestcaseUploadError('uploaded testcase file exceeds limit')
                target.write(chunk)
    except TestcaseUploadError:
        raise
    except (OSError, AttributeError) as exc:
        raise TestcaseUploadError('cannot store uploaded testcase file') from exc
    return total


def _parse_local_datetime_to_utc(value):
    local_timezone = current_app.config.get('LOCAL_TIMEZONE') if has_app_context() else None
    return parse_local_datetime_to_utc(value, local_timezone=local_timezone)


# ============ 仪表盘 ============


@admin_bp.route('/', methods=['GET'])
@admin_bp.route('/dashboard', methods=['GET'])
@admin_required
def dashboard():
    """管理后台首页"""
    # 统计信息
    user_count = User.query.count()
    problem_count = Problem.query.count()
    submission_count = Submission.query.count()
    ac_count = Submission.query.filter_by(status='AC').count()
    contest_count = Contest.query.count()

    # 今日提交数
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_submission_count = Submission.query.filter(Submission.submitted_at >= today_start).count()

    # 活跃判题任务数
    active_judge_count = JudgeTask.query.filter(
        JudgeTask.status.in_(['Queued', 'Running', 'Dispatched'])
    ).count()

    # 最近20条提交
    recent_submissions = Submission.query.order_by(Submission.submitted_at.desc()).limit(20).all()

    return render_template(
        'admin/dashboard.html',
        user_count=user_count,
        problem_count=problem_count,
        submission_count=submission_count,
        ac_count=ac_count,
        contest_count=contest_count,
        today_submission_count=today_submission_count,
        active_judge_count=active_judge_count,
        recent_submissions=recent_submissions,
    )


# ============ 题目管理 ============


@admin_bp.route('/problems', methods=['GET'])
@admin_required
def problems_list():
    """题目列表页"""
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str)
    difficulty = request.args.get('difficulty', '', type=str)

    query = Problem.query

    if q:
        query = query.filter(Problem.title.ilike(f'%{q}%'))

    if difficulty:
        query = query.filter(Problem.difficulty == difficulty)

    paginated = query.paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'admin/problems.html',
        problems=paginated.items,
        paginated=paginated,
        q=q,
        difficulty=difficulty,
    )


@admin_bp.route('/problem/create', methods=['GET', 'POST'])
@admin_required
def create_problem():
    """创建题目"""
    if request.method == 'GET':
        return render_template('admin/problem_form.html', problem=None)

    # POST 请求
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    input_description = request.form.get('input_description', '').strip()
    output_description = request.form.get('output_description', '').strip()
    sample_input = request.form.get('sample_input', '').strip()
    sample_output = request.form.get('sample_output', '').strip()

    # 验证必填字段
    if not title or not description:
        flash('标题和描述不能为空', 'error')
        return render_template('admin/problem_form.html', problem=None)

    # 获取并验证时间和内存限制
    try:
        time_limit = int(request.form.get('time_limit', 1000))
        memory_limit = int(request.form.get('memory_limit', 256))
    except ValueError:
        flash('时间和内存限制必须为整数', 'error')
        return render_template('admin/problem_form.html', problem=None)

    if not (100 <= time_limit <= 30000):
        time_limit = 1000

    if not (16 <= memory_limit <= 1024):
        memory_limit = 256

    difficulty = request.form.get('difficulty', 'medium').strip().lower()
    if difficulty not in {'easy', 'medium', 'hard'}:
        difficulty = 'medium'
    source = request.form.get('source', '').strip()
    is_public = 'is_public' in request.form

    # 创建题目
    problem = Problem(
        title=title,
        description=description,
        input_description=input_description,
        output_description=output_description,
        sample_input=sample_input,
        sample_output=sample_output,
        time_limit=time_limit,
        memory_limit=memory_limit,
        difficulty=difficulty,
        source=source,
        is_public=is_public,
        created_by=current_user.id,
    )

    db.session.add(problem)
    db.session.commit()

    # 创建测试用例目录
    testcase_dir = os.path.join(
        current_app.config['BASE_DIR'], 'data', 'problems', str(problem.id), 'testcases'
    )
    ensure_dir(testcase_dir)

    flash('题目创建成功', 'success')
    return redirect(url_for('admin.problems_list'))


@admin_bp.route('/problem/<int:problem_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_problem(problem_id):
    """编辑题目"""
    problem = Problem.query.get_or_404(problem_id)

    if request.method == 'GET':
        return render_template('admin/problem_form.html', problem=problem)

    # POST 请求
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()

    if not title or not description:
        flash('标题和描述不能为空', 'error')
        return render_template('admin/problem_form.html', problem=problem)

    try:
        time_limit = int(request.form.get('time_limit', 1000))
        memory_limit = int(request.form.get('memory_limit', 256))
    except ValueError:
        flash('时间和内存限制必须为整数', 'error')
        return render_template('admin/problem_form.html', problem=problem)

    if not (100 <= time_limit <= 30000):
        time_limit = 1000

    if not (16 <= memory_limit <= 1024):
        memory_limit = 256

    # 更新字段
    problem.title = title
    problem.description = description
    problem.input_description = request.form.get('input_description', '').strip()
    problem.output_description = request.form.get('output_description', '').strip()
    problem.sample_input = request.form.get('sample_input', '').strip()
    problem.sample_output = request.form.get('sample_output', '').strip()
    problem.time_limit = time_limit
    problem.memory_limit = memory_limit
    difficulty = request.form.get('difficulty', 'medium').strip().lower()
    problem.difficulty = difficulty if difficulty in {'easy', 'medium', 'hard'} else 'medium'
    problem.source = request.form.get('source', '').strip()
    problem.is_public = 'is_public' in request.form

    db.session.commit()
    flash('题目更新成功', 'success')
    return redirect(url_for('admin.problems_list'))


@admin_bp.route('/problem/<int:problem_id>/delete', methods=['POST'])
@admin_required
def delete_problem(problem_id):
    """删除题目"""
    # 获取确认信息
    confirmation = request.form.get('confirmation', '').strip()
    problem = Problem.query.get_or_404(problem_id)

    # 验证确认输入（应为题目标题）
    if confirmation != problem.title:
        flash('删除确认失败：输入的标题不匹配', 'error')
        return redirect(url_for('admin.problems_list'))

    if Submission.query.filter_by(problem_id=problem.id).first():
        flash('该题目已有提交记录，不能删除；请改为隐藏题目。', 'error')
        return redirect(url_for('admin.problems_list'))

    problem_id = problem.id

    # 删除关联的 ContestProblem 记录
    ContestProblem.query.filter_by(problem_id=problem_id).delete()

    # 删除题目
    db.session.delete(problem)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('题目仍有关联数据，不能删除；请改为隐藏题目。', 'error')
        return redirect(url_for('admin.problems_list'))

    # 删除磁盘上的题目目录
    problem_dir = os.path.join(current_app.config['BASE_DIR'], 'data', 'problems', str(problem_id))
    if os.path.exists(problem_dir):
        try:
            shutil.rmtree(problem_dir)
        except Exception as e:
            current_app.logger.error(f'删除题目目录失败: {e}')

    flash('题目删除成功', 'success')
    return redirect(url_for('admin.problems_list'))


@admin_bp.route('/problem/<int:problem_id>/toggle_public', methods=['POST'])
@admin_required
def toggle_problem_public(problem_id):
    """切换题目公开状态"""
    problem = Problem.query.get_or_404(problem_id)
    problem.is_public = not problem.is_public
    db.session.commit()

    status = '已公开' if problem.is_public else '已隐藏'
    flash(f'题目已{status}', 'success')
    return redirect(request.referrer or url_for('admin.problems_list'))


@admin_bp.route('/problem/<int:problem_id>/upload_testcase', methods=['POST'])
@admin_required
def upload_testcase(problem_id):
    """上传测试用例"""
    Problem.query.get_or_404(problem_id)

    # 获取上传的文件
    input_file = request.files.get('input_file')
    output_file = request.files.get('output_file')

    if not input_file or not output_file:
        flash('请同时上传 .in 和 .out 文件', 'error')
        return redirect(url_for('admin.problem_testcases', problem_id=problem_id))

    # 验证文件扩展名
    if not (input_file.filename or '').lower().endswith('.in'):
        flash('输入文件必须以.in结尾', 'error')
        return redirect(url_for('admin.problem_testcases', problem_id=problem_id))

    if not (output_file.filename or '').lower().endswith('.out'):
        flash('输出文件必须以.out结尾', 'error')
        return redirect(url_for('admin.problem_testcases', problem_id=problem_id))

    # 获取测试用例目录
    testcase_dir = os.path.join(
        current_app.config['BASE_DIR'], 'data', 'problems', str(problem_id), 'testcases'
    )
    try:
        validate_upload_filename(input_file.filename, '.in')
        validate_upload_filename(output_file.filename, '.out')
    except TestcaseUploadError:
        flash('testcase upload rejected', 'error')
        return redirect(url_for('admin.problem_testcases', problem_id=problem_id))

    # Allocate and publish the pair atomically so a failed upload cannot leave
    # an input file without its matching output file.
    temporary_paths = []
    published_paths = []
    with _TESTCASE_UPLOAD_LOCK:
        try:
            validate_testcase_directory(testcase_dir)
            if not os.path.lexists(testcase_dir):
                ensure_dir(testcase_dir)
            limits = testcase_limits(current_app.config)
            request_bytes = max(0, int(request.content_length or 0))
            if (
                available_disk_bytes(testcase_dir)
                < limits['TESTCASE_MIN_FREE_SPACE_BYTES'] + request_bytes
            ):
                raise TestcaseUploadError('insufficient free disk space')
            validate_testcase_upload(problem_id, 0, 0, limits)

            used_numbers = {
                int(os.path.splitext(name)[0])
                for name in os.listdir(testcase_dir)
                if name.rsplit('.', 1)[-1].lower() in {'in', 'out'}
                and os.path.splitext(name)[0].isdigit()
            }
            next_num = 1
            while next_num in used_numbers:
                next_num += 1

            input_temp = tempfile.NamedTemporaryFile(
                dir=testcase_dir, prefix='.upload-', suffix='.in.tmp', delete=False
            )
            input_temp.close()
            temporary_paths = [input_temp.name]
            output_temp = tempfile.NamedTemporaryFile(
                dir=testcase_dir, prefix='.upload-', suffix='.out.tmp', delete=False
            )
            output_temp.close()
            temporary_paths.append(output_temp.name)
            input_size = _save_upload_stream(
                input_file,
                input_temp.name,
                limits['TESTCASE_MAX_INPUT_BYTES'],
                limits['TESTCASE_UPLOAD_CHUNK_BYTES'],
            )
            output_size = _save_upload_stream(
                output_file,
                output_temp.name,
                limits['TESTCASE_MAX_OUTPUT_BYTES'],
                limits['TESTCASE_UPLOAD_CHUNK_BYTES'],
            )
            validate_testcase_upload(problem_id, input_size, output_size, limits)

            input_path = os.path.join(testcase_dir, f'{next_num}.in')
            output_path = os.path.join(testcase_dir, f'{next_num}.out')
            os.replace(input_temp.name, input_path)
            published_paths.append(input_path)
            os.replace(output_temp.name, output_path)
            published_paths.append(output_path)
            temporary_paths = []
            validate_testcase_storage(problem_id, limits)
            flash('测试用例上传成功', 'success')
        except Exception:
            current_app.logger.exception('Test case upload failed for problem %s', problem_id)
            for path in temporary_paths:
                try:
                    os.remove(path)
                except OSError:
                    pass
            for path in published_paths:
                try:
                    os.remove(path)
                except OSError:
                    pass
            flash('上传失败，请检查文件后重试', 'error')

    return redirect(url_for('admin.problem_testcases', problem_id=problem_id))


@admin_bp.route('/problem/<int:problem_id>/delete_testcase/<int:tc_num>', methods=['POST'])
@admin_required
def delete_testcase(problem_id, tc_num):
    """删除测试用例"""
    Problem.query.get_or_404(problem_id)

    testcase_dir = os.path.join(
        current_app.config['BASE_DIR'], 'data', 'problems', str(problem_id), 'testcases'
    )

    # 删除文件
    in_path = os.path.join(testcase_dir, f'{tc_num}.in')
    out_path = os.path.join(testcase_dir, f'{tc_num}.out')

    try:
        if os.path.exists(in_path):
            os.remove(in_path)
        if os.path.exists(out_path):
            os.remove(out_path)
        flash('测试用例删除成功', 'success')
    except Exception as e:
        flash(f'删除失败: {str(e)}', 'error')

    return redirect(url_for('admin.problem_testcases', problem_id=problem_id))


@admin_bp.route('/problem/<int:problem_id>/testcases', methods=['GET'])
@admin_required
def problem_testcases(problem_id):
    """列出题目的所有测试用例"""
    problem = Problem.query.get_or_404(problem_id)

    testcase_dir = os.path.join(
        current_app.config['BASE_DIR'], 'data', 'problems', str(problem_id), 'testcases'
    )

    testcases = []
    if os.path.isdir(testcase_dir):
        in_files = sorted(
            [f for f in os.listdir(testcase_dir) if f.endswith('.in')],
            key=lambda x: int(x.split('.')[0]),
        )

        for in_file in in_files:
            num = int(in_file.split('.')[0])
            out_file = f'{num}.out'
            in_path = os.path.join(testcase_dir, in_file)
            out_path = os.path.join(testcase_dir, out_file)

            if os.path.exists(out_path):
                testcases.append(
                    {
                        'num': num,
                        'in_size': os.path.getsize(in_path),
                        'out_size': os.path.getsize(out_path),
                    }
                )

    return render_template('admin/problem_testcases.html', problem=problem, testcases=testcases)


# ============ 竞赛管理 ============


@admin_bp.route('/contests', methods=['GET'])
@admin_required
def contests_list():
    """竞赛列表"""
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str)

    query = Contest.query

    if q:
        query = query.filter(Contest.title.ilike(f'%{q}%'))

    query = query.order_by(Contest.start_time.desc())
    paginated = query.paginate(page=page, per_page=20, error_out=False)

    contest_ids = [contest.id for contest in paginated.items]
    participant_counts = {}
    problem_counts = {}
    if contest_ids:
        participant_rows = (
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
        participant_counts = {contest_id: int(count or 0) for contest_id, count in participant_rows}
        problem_rows = (
            db.session.query(
                ContestProblem.contest_id,
                db.func.count(ContestProblem.id),
            )
            .filter(ContestProblem.contest_id.in_(contest_ids))
            .group_by(ContestProblem.contest_id)
            .all()
        )
        problem_counts = {contest_id: int(count or 0) for contest_id, count in problem_rows}

    return render_template(
        'admin/contests.html',
        contests=paginated.items,
        paginated=paginated,
        q=q,
        participant_counts=participant_counts,
        problem_counts=problem_counts,
    )


@admin_bp.route('/contest/create', methods=['GET', 'POST'])
@admin_required
def create_contest():
    """创建竞赛"""
    if request.method == 'GET':
        return render_template('admin/contest_form.html', contest=None)

    # POST 请求
    title = request.form.get('title', '').strip()

    if not title:
        flash('竞赛标题不能为空', 'error')
        return render_template('admin/contest_form.html', contest=None)

    try:
        start_time = _parse_local_datetime_to_utc(request.form.get('start_time'))
        end_time = _parse_local_datetime_to_utc(request.form.get('end_time'))
    except (ValueError, TypeError):
        flash('开始时间和结束时间格式错误', 'error')
        return render_template('admin/contest_form.html', contest=None)

    if start_time >= end_time:
        flash('开始时间必须早于结束时间', 'error')
        return render_template('admin/contest_form.html', contest=None)

    if start_time < datetime.utcnow():
        flash('开始时间不能早于当前时间', 'error')
        return render_template('admin/contest_form.html', contest=None)

    description = request.form.get('description', '').strip()
    is_public = 'is_public' in request.form
    is_sealed = 'is_sealed' in request.form
    password = request.form.get('password', '').strip()

    try:
        max_participants = int(request.form.get('max_participants', 0))
    except ValueError:
        max_participants = 0
    max_participants = max(0, min(max_participants, 100000))

    contest = Contest(
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
        is_public=is_public,
        is_sealed=is_sealed,
        password=password,
        max_participants=max_participants,
        created_by=current_user.id,
    )

    db.session.add(contest)
    db.session.commit()

    flash('竞赛创建成功', 'success')
    return redirect(url_for('admin.edit_contest', contest_id=contest.id))


@admin_bp.route('/contest/<int:contest_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_contest(contest_id):
    """编辑竞赛"""
    contest = Contest.query.get_or_404(contest_id)

    if request.method == 'GET':
        return render_template('admin/contest_form.html', contest=contest)

    # POST 请求
    title = request.form.get('title', '').strip()

    if not title:
        flash('竞赛标题不能为空', 'error')
        return render_template('admin/contest_form.html', contest=contest)

    try:
        start_time = _parse_local_datetime_to_utc(request.form.get('start_time'))
        end_time = _parse_local_datetime_to_utc(request.form.get('end_time'))
    except (ValueError, TypeError):
        flash('开始时间和结束时间格式错误', 'error')
        return render_template('admin/contest_form.html', contest=contest)

    if start_time >= end_time:
        flash('开始时间必须早于结束时间', 'error')
        return render_template('admin/contest_form.html', contest=contest)

    # 已开始的竞赛只能修改某些字段
    if contest.status in ['Running', 'Ended']:
        flash('已开始的竞赛不能修改开始时间', 'warning')
        start_time = contest.start_time

    description = request.form.get('description', '').strip()
    is_public = 'is_public' in request.form
    is_sealed = 'is_sealed' in request.form
    password = request.form.get('password', '').strip()

    try:
        max_participants = int(request.form.get('max_participants', 0))
    except ValueError:
        max_participants = 0
    max_participants = max(0, min(max_participants, 100000))

    contest.title = title
    contest.description = description
    contest.start_time = start_time
    contest.end_time = end_time
    contest.is_public = is_public
    contest.is_sealed = is_sealed
    contest.password = password
    contest.max_participants = max_participants

    db.session.commit()
    flash('竞赛更新成功', 'success')
    return redirect(url_for('admin.contests_list'))


@admin_bp.route('/contest/<int:contest_id>/delete', methods=['POST'])
@admin_required
def delete_contest(contest_id):
    """删除竞赛"""
    contest = Contest.query.get_or_404(contest_id)
    confirmation = request.form.get('confirmation', '').strip()

    if confirmation != contest.title:
        flash('删除确认失败：输入的标题不匹配', 'error')
        return redirect(url_for('admin.contests_list'))

    if Submission.query.filter_by(contest_id=contest_id).first():
        flash('该竞赛已有提交记录，不能删除；请改为取消公开或封榜。', 'error')
        return redirect(url_for('admin.contests_list'))

    # 删除关联数据
    ContestProblem.query.filter_by(contest_id=contest_id).delete()
    ContestParticipant.query.filter_by(contest_id=contest_id).delete()

    db.session.delete(contest)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('竞赛仍有关联数据，不能删除；请改为取消公开或封榜。', 'error')
        return redirect(url_for('admin.contests_list'))

    flash('竞赛删除成功', 'success')
    return redirect(url_for('admin.contests_list'))


@admin_bp.route('/contest/<int:contest_id>/problems', methods=['GET', 'POST'])
@admin_required
def contest_problems(contest_id):
    """管理竞赛题目"""
    contest = Contest.query.get_or_404(contest_id)

    if request.method == 'POST':
        # 添加题目
        problem_id = request.form.get('problem_id', type=int)
        alias = request.form.get('alias', '').strip()

        if not problem_id:
            flash('请选择题目', 'error')
            return redirect(url_for('admin.contest_problems', contest_id=contest_id))

        Problem.query.get_or_404(problem_id)

        # 检查是否已添加
        if ContestProblem.query.filter_by(contest_id=contest_id, problem_id=problem_id).first():
            flash('该题目已在竞赛中', 'error')
            return redirect(url_for('admin.contest_problems', contest_id=contest_id))

        # 计算显示顺序
        max_order = (
            db.session.query(db.func.max(ContestProblem.display_order))
            .filter(ContestProblem.contest_id == contest_id)
            .scalar()
            or -1
        )

        cp = ContestProblem(
            contest_id=contest_id,
            problem_id=problem_id,
            display_order=max_order + 1,
            alias=alias if alias else None,
        )

        db.session.add(cp)
        db.session.commit()

        flash('题目添加成功', 'success')
        return redirect(url_for('admin.contest_problems', contest_id=contest_id))

    # GET 请求
    contest_problems = (
        ContestProblem.query.filter_by(contest_id=contest_id)
        .order_by(ContestProblem.display_order)
        .all()
    )

    # 获取已添加的题目ID
    problem_ids = [cp.problem_id for cp in contest_problems]

    # 获取可用题目
    available_problems = Problem.query.filter(
        ~Problem.id.in_(problem_ids) if problem_ids else True
    ).all()

    return render_template(
        'admin/contest_problems.html',
        contest=contest,
        contest_problems=contest_problems,
        available_problems=available_problems,
    )


@admin_bp.route('/contest/<int:contest_id>/problem/<int:problem_id>/remove', methods=['POST'])
@admin_required
def remove_contest_problem(contest_id, problem_id):
    """从竞赛移除题目"""
    cp = ContestProblem.query.filter_by(contest_id=contest_id, problem_id=problem_id).first_or_404()
    db.session.delete(cp)
    db.session.commit()

    flash('题目已移除', 'success')
    return redirect(url_for('admin.contest_problems', contest_id=contest_id))


@admin_bp.route('/contest/<int:contest_id>/participants', methods=['GET'])
@admin_required
def contest_participants(contest_id):
    """管理竞赛参赛者"""
    contest = Contest.query.get_or_404(contest_id)
    participants = ContestParticipant.query.filter_by(contest_id=contest_id).all()

    return render_template(
        'admin/contest_participants.html', contest=contest, participants=participants
    )


@admin_bp.route('/contest/<int:contest_id>/participant/add', methods=['POST'])
@admin_required
def add_participant(contest_id):
    """添加参赛者"""
    contest = Contest.query.get_or_404(contest_id)

    # 获取用户
    user_id = request.form.get('user_id', type=int)
    user = None

    if user_id:
        user = db.session.get(User, user_id)
    else:
        username = request.form.get('username', '').strip()
        if username:
            user = User.query.filter_by(username=username).first()

    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('admin.contest_participants', contest_id=contest_id))

    # 检查是否已参加
    if ContestParticipant.query.filter_by(contest_id=contest_id, user_id=user.id).first():
        flash('该用户已是参赛者', 'error')
        return redirect(url_for('admin.contest_participants', contest_id=contest_id))

    # 检查人数限制
    if contest.max_participants > 0:
        if contest.participant_count >= contest.max_participants:
            flash('参赛人数已达上限', 'error')
            return redirect(url_for('admin.contest_participants', contest_id=contest_id))

    cp = ContestParticipant(contest_id=contest_id, user_id=user.id)
    db.session.add(cp)
    db.session.commit()

    flash('参赛者添加成功', 'success')
    return redirect(url_for('admin.contest_participants', contest_id=contest_id))


@admin_bp.route('/contest/<int:contest_id>/participant/<int:user_id>/disqualify', methods=['POST'])
@admin_required
def disqualify_participant(contest_id, user_id):
    """切换参赛者资格状态"""
    cp = ContestParticipant.query.filter_by(contest_id=contest_id, user_id=user_id).first_or_404()
    cp.is_disqualified = not cp.is_disqualified
    db.session.commit()

    status = '已取消资格' if cp.is_disqualified else '已恢复资格'
    flash(f'参赛者{status}', 'success')
    return redirect(url_for('admin.contest_participants', contest_id=contest_id))


@admin_bp.route('/contest/<int:contest_id>/participant/<int:user_id>/remove', methods=['POST'])
@admin_required
def remove_participant(contest_id, user_id):
    """移除参赛者"""
    cp = ContestParticipant.query.filter_by(contest_id=contest_id, user_id=user_id).first_or_404()
    db.session.delete(cp)
    db.session.commit()

    flash('参赛者已移除', 'success')
    return redirect(url_for('admin.contest_participants', contest_id=contest_id))


@admin_bp.route('/contest/<int:contest_id>/submissions', methods=['GET'])
@admin_required
def contest_submissions(contest_id):
    """查看竞赛提交记录"""
    contest = Contest.query.get_or_404(contest_id)
    page = request.args.get('page', 1, type=int)

    query = Submission.query.filter_by(contest_id=contest_id)

    paginated = query.order_by(Submission.submitted_at.desc()).paginate(
        page=page, per_page=30, error_out=False
    )

    return render_template(
        'admin/contest_submissions.html',
        contest=contest,
        submissions=paginated.items,
        paginated=paginated,
    )


@admin_bp.route('/contest/<int:contest_id>/ranklist', methods=['GET'])
@admin_required
def contest_ranklist(contest_id):
    """查看竞赛排行榜"""
    contest = Contest.query.get_or_404(contest_id)
    ranklist = contest.get_ranklist()

    return render_template('admin/contest_ranklist.html', contest=contest, ranklist=ranklist)


# ============ 用户管理 ============


@admin_bp.route('/users', methods=['GET'])
@admin_required
def users_list():
    """用户列表"""
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str)
    role = request.args.get('role', '', type=str)

    query = User.query

    if q:
        query = query.filter(db.or_(User.username.ilike(f'%{q}%'), User.email.ilike(f'%{q}%')))

    if role:
        query = query.filter(User.role == role)

    paginated = query.paginate(page=page, per_page=20, error_out=False)

    user_ids = [user.id for user in paginated.items]
    submission_counts = {}
    accepted_counts = {}
    if user_ids:
        submission_rows = (
            db.session.query(Submission.user_id, db.func.count(Submission.id))
            .filter(Submission.user_id.in_(user_ids))
            .group_by(Submission.user_id)
            .all()
        )
        accepted_rows = (
            db.session.query(Submission.user_id, db.func.count(Submission.id))
            .filter(Submission.user_id.in_(user_ids), Submission.status == 'AC')
            .group_by(Submission.user_id)
            .all()
        )
        submission_counts = {user_id: int(count or 0) for user_id, count in submission_rows}
        accepted_counts = {user_id: int(count or 0) for user_id, count in accepted_rows}

    return render_template(
        'admin/users.html',
        users=paginated.items,
        paginated=paginated,
        q=q,
        role=role,
        submission_counts=submission_counts,
        accepted_counts=accepted_counts,
    )


@admin_bp.route('/user/<int:user_id>/detail', methods=['GET'])
@admin_required
def user_detail(user_id):
    """用户详情页"""
    user = User.query.get_or_404(user_id)

    # 统计信息
    total_submissions = Submission.query.filter_by(user_id=user_id).count()
    ac_submissions = Submission.query.filter_by(user_id=user_id, status='AC').count()
    ac_rate = (ac_submissions / total_submissions * 100) if total_submissions > 0 else 0

    # 语言分布
    language_dist = (
        db.session.query(Submission.language, db.func.count(Submission.id))
        .filter_by(user_id=user_id)
        .group_by(Submission.language)
        .all()
    )

    # 最近提交
    recent_submissions = (
        Submission.query.filter_by(user_id=user_id)
        .order_by(Submission.submitted_at.desc())
        .limit(20)
        .all()
    )

    # 参加的竞赛
    participated_contests = (
        db.session.query(Contest)
        .join(ContestParticipant)
        .filter(ContestParticipant.user_id == user_id)
        .all()
    )

    return render_template(
        'admin/user_detail.html',
        user=user,
        total_submissions=total_submissions,
        ac_submissions=ac_submissions,
        ac_rate=ac_rate,
        language_dist=language_dist,
        recent_submissions=recent_submissions,
        participated_contests=participated_contests,
    )


@admin_bp.route('/user/<int:user_id>/toggle_active', methods=['POST'])
@admin_required
def toggle_user_active(user_id):
    """切换用户状态"""
    user = User.query.get_or_404(user_id)
    if not AccountService.toggle_active(user, current_user):
        flash(
            'This account change would remove your access or the last active administrator.',
            'error',
        )
        return redirect(request.referrer or url_for('admin.users_list'))

    status = '已启用' if user.is_active else '已禁用'
    flash(f'用户{status}', 'success')
    return redirect(request.referrer or url_for('admin.users_list'))


@admin_bp.route('/user/<int:user_id>/toggle_role', methods=['POST'])
@admin_required
def toggle_user_role(user_id):
    """切换用户角色"""
    if user_id == current_user.id:
        flash('不能修改自己的角色', 'error')
        return redirect(request.referrer or url_for('admin.users_list'))

    user = User.query.get_or_404(user_id)
    if not AccountService.toggle_role(user, current_user):
        flash(
            'This account change would remove your access or the last active administrator.',
            'error',
        )
        return redirect(request.referrer or url_for('admin.users_list'))

    role_name = '管理员' if user.role == 'admin' else '普通用户'
    flash(f'用户角色已更改为 {role_name}', 'success')
    return redirect(request.referrer or url_for('admin.users_list'))


@admin_bp.route('/user/<int:user_id>/reset_password', methods=['POST'])
@admin_required
def reset_user_password(user_id):
    user = User.query.get_or_404(user_id)
    temporary_password = AccountService.reset_password(user)
    response = current_app.make_response(
        render_template(
            'admin/password_reset.html',
            user=user,
            temporary_password=temporary_password,
        )
    )
    response.headers['Cache-Control'] = 'no-store'
    return response


# ============ 提交和判题 ============


@admin_bp.route('/submissions', methods=['GET'])
@admin_required
def submissions_list():
    """全局提交列表"""
    page = request.args.get('page', 1, type=int)
    user_id = request.args.get('user_id', type=int)
    problem_id = request.args.get('problem_id', type=int)
    status = request.args.get('status', type=str)

    query = Submission.query

    if user_id:
        query = query.filter_by(user_id=user_id)
    if problem_id:
        query = query.filter_by(problem_id=problem_id)
    if status:
        query = query.filter_by(status=status)

    paginated = query.order_by(Submission.submitted_at.desc()).paginate(
        page=page, per_page=30, error_out=False
    )

    return render_template(
        'admin/submissions.html', submissions=paginated.items, paginated=paginated
    )


@admin_bp.route('/submission/<int:submission_id>/rejudge', methods=['POST'])
@admin_required
def rejudge_submission(submission_id):
    """重新判题"""
    submission = Submission.query.get_or_404(submission_id)

    # 删除旧的 JudgeTask
    JudgeTask.query.filter_by(submission_id=submission_id).delete()

    # 重置提交状态
    submission.status = 'Pending'
    submission.judged_at = None
    db.session.commit()

    # 提交新的判题任务
    if hasattr(current_app, 'judge_engine'):
        current_app.judge_engine.submit_judge_task(submission_id)

    flash('已重新提交判题任务', 'success')
    return redirect(request.referrer or url_for('admin.submissions_list'))


_JUDGE_UNAVAILABLE = '不可用'


def _safe_attr(value, name, default=_JUDGE_UNAVAILABLE):
    try:
        return getattr(value, name)
    except Exception:
        return default


def _safe_call(value, name, default=_JUDGE_UNAVAILABLE):
    try:
        return getattr(value, name)()
    except Exception:
        return default


def _policy_value(engine, policy_name, config_name):
    policy = _safe_attr(engine, 'policy', None)
    value = _safe_attr(policy, policy_name)
    if value == _JUDGE_UNAVAILABLE:
        return current_app.config.get(config_name, _JUDGE_UNAVAILABLE)
    return value


def _format_limit(value, suffix=''):
    if value == _JUDGE_UNAVAILABLE:
        return _JUDGE_UNAVAILABLE
    try:
        if isinstance(value, float) and not value.is_integer():
            value = f'{value:.1f}'
        else:
            value = str(int(value))
    except (TypeError, ValueError):
        return _JUDGE_UNAVAILABLE
    return f'{value}{suffix}'


def _format_cpu(value):
    if value == _JUDGE_UNAVAILABLE:
        return _JUDGE_UNAVAILABLE
    try:
        return f'{float(value):.1f}%'
    except (TypeError, ValueError):
        return _JUDGE_UNAVAILABLE


def _format_memory(value):
    return _format_limit(value, ' MiB')


def _snapshot_value(snapshot, name):
    if isinstance(snapshot, dict):
        return snapshot.get(name, _JUDGE_UNAVAILABLE)
    return _safe_attr(snapshot, name)


def _judge_observability(engine):
    queue = _safe_attr(engine, 'task_queue', None)
    queue_depth = _safe_call(queue, 'qsize')
    queue_capacity = _policy_value(engine, 'queue_maxsize', 'JUDGE_QUEUE_MAXSIZE')
    if queue_depth == _JUDGE_UNAVAILABLE or queue_capacity == _JUDGE_UNAVAILABLE:
        queue_display = _JUDGE_UNAVAILABLE
    else:
        queue_display = f'{queue_depth} / {_format_limit(queue_capacity)}'

    guard = _safe_attr(engine, 'host_guard', None)
    snapshot = _safe_call(guard, 'snapshot')
    host_cpu = _format_cpu(_snapshot_value(snapshot, 'cpu_percent'))
    available_memory = _format_memory(_snapshot_value(snapshot, 'available_memory_mb'))

    pause_reason = _safe_attr(engine, 'dispatch_pause_reason')
    if pause_reason == '':
        pause_reason = '-'

    worker_count = _safe_attr(engine, 'max_workers')
    if worker_count == _JUDGE_UNAVAILABLE:
        worker_count = _policy_value(engine, 'max_workers', 'MAX_JUDGE_WORKERS')
    if engine is None:
        worker_count = _JUDGE_UNAVAILABLE

    max_cpu = _safe_attr(guard, 'max_cpu_percent')
    if max_cpu == _JUDGE_UNAVAILABLE:
        max_cpu = current_app.config.get('JUDGE_HOST_MAX_CPU_PERCENT', _JUDGE_UNAVAILABLE)
    min_memory = _safe_attr(guard, 'min_available_memory_mb')
    if min_memory == _JUDGE_UNAVAILABLE:
        min_memory = current_app.config.get(
            'JUDGE_HOST_MIN_AVAILABLE_MEMORY_MB', _JUDGE_UNAVAILABLE
        )

    config_limits = [
        {'label': t('admin.worker_threads'), 'value': _format_limit(worker_count)},
        {'label': t('admin.queue_tasks'), 'value': _format_limit(queue_capacity)},
        {
            'label': t('admin.active_tasks'),
            'value': _format_limit(current_app.config.get('JUDGE_TOTAL_ACTIVE_MAX')),
        },
        {
            'label': 'User active task cap',
            'value': _format_limit(current_app.config.get('JUDGE_USER_ACTIVE_MAX')),
        },
        {'label': 'CPU cap', 'value': _format_cpu(max_cpu)},
        {'label': 'Minimum available memory', 'value': _format_memory(min_memory)},
        {
            'label': t('admin.time'),
            'value': _format_limit(
                _policy_value(engine, 'max_time_limit_ms', 'MAX_TIME_LIMIT_MS'), ' ms'
            ),
        },
        {
            'label': t('admin.memory'),
            'value': _format_memory(
                _policy_value(engine, 'max_memory_limit_mb', 'MAX_MEMORY_LIMIT_MB')
            ),
        },
        {
            'label': 'Sandbox processes',
            'value': _format_limit(_policy_value(engine, 'max_processes', 'SANDBOX_MAX_PROCESSES')),
        },
        {
            'label': 'Output bytes',
            'value': _format_limit(_policy_value(engine, 'max_output_size', 'MAX_OUTPUT_SIZE')),
        },
        {
            'label': 'Workspace bytes',
            'value': _format_limit(
                _policy_value(engine, 'max_workspace_bytes', 'SANDBOX_MAX_WORKSPACE_BYTES')
            ),
        },
        {
            'label': 'Workspace files',
            'value': _format_limit(
                _policy_value(engine, 'max_workspace_files', 'SANDBOX_MAX_WORKSPACE_FILES')
            ),
        },
    ]

    return {
        'engine_available': engine is not None,
        'running': bool(_safe_attr(engine, 'is_running', False)),
        'worker_count': worker_count,
        'queue_display': queue_display,
        'host_cpu': host_cpu,
        'available_memory': available_memory,
        'dispatch_pause_reason': pause_reason,
        'config_limits': config_limits,
    }


@admin_bp.route('/judge_status', methods=['GET'])
@admin_required
def judge_status():
    """判题引擎状态"""
    # 获取引擎状态
    running = False
    worker_count = 0
    queue_size = 0
    active_tasks = 0

    engine = getattr(current_app, 'judge_engine', None)
    observability = _judge_observability(engine)
    if observability['engine_available']:
        running = observability['running']
        worker_count = observability['worker_count']

    # 统计队列和任务
    queue_size = JudgeTask.query.filter_by(status='Queued').count()
    active_tasks = JudgeTask.query.filter(JudgeTask.status.in_(['Dispatched', 'Running'])).count()

    # 获取活跃任务列表
    active_task_list = (
        JudgeTask.query.filter(JudgeTask.status.in_(['Dispatched', 'Running']))
        .order_by(JudgeTask.started_at.desc())
        .limit(10)
        .all()
    )

    # 获取排队任务列表
    queued_task_list = (
        JudgeTask.query.filter_by(status='Queued').order_by(JudgeTask.created_at).limit(10).all()
    )

    # 获取最近完成的任务
    recent_tasks = (
        JudgeTask.query.filter_by(status='Completed')
        .order_by(JudgeTask.completed_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        'admin/judge_status.html',
        running=running,
        worker_count=worker_count,
        queue_size=queue_size,
        active_tasks=active_tasks,
        active_task_list=active_task_list,
        queued_task_list=queued_task_list,
        recent_tasks=recent_tasks,
        judge_observability=observability,
    )
