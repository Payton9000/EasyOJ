"""OJ系统管理后台模块

提供题目、竞赛、用户、提交记录等管理功能
"""
import os
import shutil
import random
import string
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, abort
from flask_login import login_required, current_user
from app import db
from app.models import User, Problem, Submission, JudgeTask, Contest, ContestProblem, ContestParticipant
from app.utils.decorators import admin_required
from app.utils.file_utils import ensure_dir

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _check_admin():
    """检查管理员权限的辅助函数"""
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


# ============ 仪表盘 ============

@admin_bp.route('/', methods=['GET'])
@admin_bp.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    """管理后台首页"""
    _check_admin()
    
    # 统计信息
    user_count = User.query.count()
    problem_count = Problem.query.count()
    submission_count = Submission.query.count()
    ac_count = Submission.query.filter_by(status='AC').count()
    contest_count = Contest.query.count()
    
    # 今日提交数
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_submission_count = Submission.query.filter(
        Submission.submitted_at >= today_start
    ).count()
    
    # 活跃判题任务数
    active_judge_count = JudgeTask.query.filter(
        JudgeTask.status.in_(['Queued', 'Running', 'Dispatched'])
    ).count()
    
    # 最近20条提交
    recent_submissions = Submission.query.order_by(
        Submission.submitted_at.desc()
    ).limit(20).all()
    
    return render_template('admin/dashboard.html',
                         user_count=user_count,
                         problem_count=problem_count,
                         submission_count=submission_count,
                         ac_count=ac_count,
                         contest_count=contest_count,
                         today_submission_count=today_submission_count,
                         active_judge_count=active_judge_count,
                         recent_submissions=recent_submissions)


# ============ 题目管理 ============

@admin_bp.route('/problems', methods=['GET'])
@login_required
def problems_list():
    """题目列表页"""
    _check_admin()
    
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str)
    difficulty = request.args.get('difficulty', '', type=str)
    
    query = Problem.query
    
    if q:
        query = query.filter(Problem.title.ilike(f'%{q}%'))
    
    if difficulty:
        query = query.filter(Problem.difficulty == difficulty)
    
    paginated = query.paginate(page=page, per_page=20, error_out=False)
    
    return render_template('admin/problems.html',
                         problems=paginated.items,
                         paginated=paginated,
                         q=q,
                         difficulty=difficulty)


@admin_bp.route('/problem/create', methods=['GET', 'POST'])
@login_required
def create_problem():
    """创建题目"""
    _check_admin()
    
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
    
    difficulty = request.form.get('difficulty', 'medium')
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
        created_by=current_user.id
    )
    
    db.session.add(problem)
    db.session.commit()
    
    # 创建测试用例目录
    testcase_dir = os.path.join(current_app.config['BASE_DIR'], 
                                'data', 'problems', str(problem.id), 'testcases')
    ensure_dir(testcase_dir)
    
    flash('题目创建成功', 'success')
    return redirect(url_for('admin.problems_list'))


@admin_bp.route('/problem/<int:problem_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_problem(problem_id):
    """编辑题目"""
    _check_admin()
    
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
    problem.difficulty = request.form.get('difficulty', 'medium')
    problem.source = request.form.get('source', '').strip()
    problem.is_public = 'is_public' in request.form
    
    db.session.commit()
    flash('题目更新成功', 'success')
    return redirect(url_for('admin.problems_list'))


@admin_bp.route('/problem/<int:problem_id>/delete', methods=['POST'])
@login_required
def delete_problem(problem_id):
    """删除题目"""
    _check_admin()
    
    # 获取确认信息
    confirmation = request.form.get('confirmation', '').strip()
    problem = Problem.query.get_or_404(problem_id)
    
    # 验证确认输入（应为题目标题）
    if confirmation != problem.title:
        flash('删除确认失败：输入的标题不匹配', 'error')
        return redirect(url_for('admin.problems_list'))
    
    problem_id = problem.id
    
    # 删除关联的 ContestProblem 记录
    ContestProblem.query.filter_by(problem_id=problem_id).delete()
    
    # 删除题目
    db.session.delete(problem)
    db.session.commit()
    
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
@login_required
def toggle_problem_public(problem_id):
    """切换题目公开状态"""
    _check_admin()
    
    problem = Problem.query.get_or_404(problem_id)
    problem.is_public = not problem.is_public
    db.session.commit()
    
    status = '已公开' if problem.is_public else '已隐藏'
    flash(f'题目已{status}', 'success')
    return redirect(request.referrer or url_for('admin.problems_list'))


@admin_bp.route('/problem/<int:problem_id>/upload_testcase', methods=['POST'])
@login_required
def upload_testcase(problem_id):
    """上传测试用例"""
    _check_admin()
    
    problem = Problem.query.get_or_404(problem_id)
    
    # 获取上传的文件
    input_file = request.files.get('input_file')
    output_file = request.files.get('output_file')
    
    if not input_file or not output_file:
        flash('请同时上传 .in 和 .out 文件', 'error')
        return redirect(url_for('admin.problem_testcases', problem_id=problem_id))
    
    # 验证文件扩展名
    if not input_file.filename.endswith('.in'):
        flash('输入文件必须以.in结尾', 'error')
        return redirect(url_for('admin.problem_testcases', problem_id=problem_id))
    
    if not output_file.filename.endswith('.out'):
        flash('输出文件必须以.out结尾', 'error')
        return redirect(url_for('admin.problem_testcases', problem_id=problem_id))
    
    # 获取测试用例目录
    testcase_dir = os.path.join(current_app.config['BASE_DIR'],
                                'data', 'problems', str(problem_id), 'testcases')
    ensure_dir(testcase_dir)
    
    # 获取下一个测试用例编号
    in_files = [f for f in os.listdir(testcase_dir) if f.endswith('.in')]
    next_num = len(in_files) + 1
    
    # 保存文件
    try:
        input_file.save(os.path.join(testcase_dir, f'{next_num}.in'))
        output_file.save(os.path.join(testcase_dir, f'{next_num}.out'))
        flash('测试用例上传成功', 'success')
    except Exception as e:
        flash(f'上传失败: {str(e)}', 'error')
    
    return redirect(url_for('admin.problem_testcases', problem_id=problem_id))


@admin_bp.route('/problem/<int:problem_id>/delete_testcase/<int:tc_num>', methods=['POST'])
@login_required
def delete_testcase(problem_id, tc_num):
    """删除测试用例"""
    _check_admin()
    
    problem = Problem.query.get_or_404(problem_id)
    
    testcase_dir = os.path.join(current_app.config['BASE_DIR'],
                                'data', 'problems', str(problem_id), 'testcases')
    
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
@login_required
def problem_testcases(problem_id):
    """列出题目的所有测试用例"""
    _check_admin()
    
    problem = Problem.query.get_or_404(problem_id)
    
    testcase_dir = os.path.join(current_app.config['BASE_DIR'],
                                'data', 'problems', str(problem_id), 'testcases')
    
    testcases = []
    if os.path.isdir(testcase_dir):
        in_files = sorted([f for f in os.listdir(testcase_dir) if f.endswith('.in')],
                         key=lambda x: int(x.split('.')[0]))
        
        for in_file in in_files:
            num = int(in_file.split('.')[0])
            out_file = f'{num}.out'
            in_path = os.path.join(testcase_dir, in_file)
            out_path = os.path.join(testcase_dir, out_file)
            
            if os.path.exists(out_path):
                testcases.append({
                    'num': num,
                    'in_size': os.path.getsize(in_path),
                    'out_size': os.path.getsize(out_path)
                })
    
    return render_template('admin/problem_testcases.html',
                         problem=problem,
                         testcases=testcases)


# ============ 竞赛管理 ============

@admin_bp.route('/contests', methods=['GET'])
@login_required
def contests_list():
    """竞赛列表"""
    _check_admin()
    
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str)
    
    query = Contest.query
    
    if q:
        query = query.filter(Contest.title.ilike(f'%{q}%'))
    
    query = query.order_by(Contest.start_time.desc())
    paginated = query.paginate(page=page, per_page=20, error_out=False)
    
    return render_template('admin/contests.html',
                         contests=paginated.items,
                         paginated=paginated,
                         q=q)


@admin_bp.route('/contest/create', methods=['GET', 'POST'])
@login_required
def create_contest():
    """创建竞赛"""
    _check_admin()
    
    if request.method == 'GET':
        return render_template('admin/contest_form.html', contest=None)
    
    # POST 请求
    title = request.form.get('title', '').strip()
    
    if not title:
        flash('竞赛标题不能为空', 'error')
        return render_template('admin/contest_form.html', contest=None)
    
    try:
        start_time = datetime.fromisoformat(request.form.get('start_time'))
        end_time = datetime.fromisoformat(request.form.get('end_time'))
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
    
    contest = Contest(
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
        is_public=is_public,
        is_sealed=is_sealed,
        password=password,
        max_participants=max_participants,
        created_by=current_user.id
    )
    
    db.session.add(contest)
    db.session.commit()
    
    flash('竞赛创建成功', 'success')
    return redirect(url_for('admin.edit_contest', contest_id=contest.id))


@admin_bp.route('/contest/<int:contest_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_contest(contest_id):
    """编辑竞赛"""
    _check_admin()
    
    contest = Contest.query.get_or_404(contest_id)
    
    if request.method == 'GET':
        return render_template('admin/contest_form.html', contest=contest)
    
    # POST 请求
    title = request.form.get('title', '').strip()
    
    if not title:
        flash('竞赛标题不能为空', 'error')
        return render_template('admin/contest_form.html', contest=contest)
    
    try:
        start_time = datetime.fromisoformat(request.form.get('start_time'))
        end_time = datetime.fromisoformat(request.form.get('end_time'))
    except (ValueError, TypeError):
        flash('开始时间和结束时间格式错误', 'error')
        return render_template('admin/contest_form.html', contest=contest)
    
    if start_time >= end_time:
        flash('开始时间必须早于结束时间', 'error')
        return render_template('admin/contest_form.html', contest=contest)
    
    # 已开始的竞赛只能修改某些字段
    if contest.status in ['Running', 'Ended']:
        flash('已开始的竞赛不能修改开始时间', 'info')
        start_time = contest.start_time
    
    description = request.form.get('description', '').strip()
    is_public = 'is_public' in request.form
    is_sealed = 'is_sealed' in request.form
    password = request.form.get('password', '').strip()
    
    try:
        max_participants = int(request.form.get('max_participants', 0))
    except ValueError:
        max_participants = 0
    
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
@login_required
def delete_contest(contest_id):
    """删除竞赛"""
    _check_admin()
    
    contest = Contest.query.get_or_404(contest_id)
    confirmation = request.form.get('confirmation', '').strip()
    
    if confirmation != contest.title:
        flash('删除确认失败：输入的标题不匹配', 'error')
        return redirect(url_for('admin.contests_list'))
    
    # 删除关联数据
    ContestProblem.query.filter_by(contest_id=contest_id).delete()
    ContestParticipant.query.filter_by(contest_id=contest_id).delete()
    
    db.session.delete(contest)
    db.session.commit()
    
    flash('竞赛删除成功', 'success')
    return redirect(url_for('admin.contests_list'))


@admin_bp.route('/contest/<int:contest_id>/problems', methods=['GET', 'POST'])
@login_required
def contest_problems(contest_id):
    """管理竞赛题目"""
    _check_admin()
    
    contest = Contest.query.get_or_404(contest_id)
    
    if request.method == 'POST':
        # 添加题目
        problem_id = request.form.get('problem_id', type=int)
        alias = request.form.get('alias', '').strip()
        
        if not problem_id:
            flash('请选择题目', 'error')
            return redirect(url_for('admin.contest_problems', contest_id=contest_id))
        
        problem = Problem.query.get_or_404(problem_id)
        
        # 检查是否已添加
        if ContestProblem.query.filter_by(contest_id=contest_id, problem_id=problem_id).first():
            flash('该题目已在竞赛中', 'error')
            return redirect(url_for('admin.contest_problems', contest_id=contest_id))
        
        # 计算显示顺序
        max_order = db.session.query(db.func.max(ContestProblem.display_order)).filter(
            ContestProblem.contest_id == contest_id
        ).scalar() or -1
        
        cp = ContestProblem(
            contest_id=contest_id,
            problem_id=problem_id,
            display_order=max_order + 1,
            alias=alias if alias else None
        )
        
        db.session.add(cp)
        db.session.commit()
        
        flash('题目添加成功', 'success')
        return redirect(url_for('admin.contest_problems', contest_id=contest_id))
    
    # GET 请求
    contest_problems = ContestProblem.query.filter_by(contest_id=contest_id).order_by(
        ContestProblem.display_order
    ).all()
    
    # 获取已添加的题目ID
    problem_ids = [cp.problem_id for cp in contest_problems]
    
    # 获取可用题目
    available_problems = Problem.query.filter(
        ~Problem.id.in_(problem_ids) if problem_ids else True
    ).all()
    
    return render_template('admin/contest_problems.html',
                         contest=contest,
                         contest_problems=contest_problems,
                         available_problems=available_problems)


@admin_bp.route('/contest/<int:contest_id>/problem/<int:problem_id>/remove', methods=['POST'])
@login_required
def remove_contest_problem(contest_id, problem_id):
    """从竞赛移除题目"""
    _check_admin()
    
    cp = ContestProblem.query.filter_by(contest_id=contest_id, problem_id=problem_id).first_or_404()
    db.session.delete(cp)
    db.session.commit()
    
    flash('题目已移除', 'success')
    return redirect(url_for('admin.contest_problems', contest_id=contest_id))


@admin_bp.route('/contest/<int:contest_id>/participants', methods=['GET'])
@login_required
def contest_participants(contest_id):
    """管理竞赛参赛者"""
    _check_admin()
    
    contest = Contest.query.get_or_404(contest_id)
    participants = ContestParticipant.query.filter_by(contest_id=contest_id).all()
    
    return render_template('admin/contest_participants.html',
                         contest=contest,
                         participants=participants)


@admin_bp.route('/contest/<int:contest_id>/participant/add', methods=['POST'])
@login_required
def add_participant(contest_id):
    """添加参赛者"""
    _check_admin()
    
    contest = Contest.query.get_or_404(contest_id)
    
    # 获取用户
    user_id = request.form.get('user_id', type=int)
    user = None
    
    if user_id:
        user = User.query.get(user_id)
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
@login_required
def disqualify_participant(contest_id, user_id):
    """切换参赛者资格状态"""
    _check_admin()
    
    cp = ContestParticipant.query.filter_by(contest_id=contest_id, user_id=user_id).first_or_404()
    cp.is_disqualified = not cp.is_disqualified
    db.session.commit()
    
    status = '已取消资格' if cp.is_disqualified else '已恢复资格'
    flash(f'参赛者{status}', 'success')
    return redirect(url_for('admin.contest_participants', contest_id=contest_id))


@admin_bp.route('/contest/<int:contest_id>/participant/<int:user_id>/remove', methods=['POST'])
@login_required
def remove_participant(contest_id, user_id):
    """移除参赛者"""
    _check_admin()
    
    cp = ContestParticipant.query.filter_by(contest_id=contest_id, user_id=user_id).first_or_404()
    db.session.delete(cp)
    db.session.commit()
    
    flash('参赛者已移除', 'success')
    return redirect(url_for('admin.contest_participants', contest_id=contest_id))


@admin_bp.route('/contest/<int:contest_id>/submissions', methods=['GET'])
@login_required
def contest_submissions(contest_id):
    """查看竞赛提交记录"""
    _check_admin()
    
    contest = Contest.query.get_or_404(contest_id)
    page = request.args.get('page', 1, type=int)
    
    query = Submission.query.filter_by(contest_id=contest_id)
    
    paginated = query.order_by(Submission.submitted_at.desc()).paginate(
        page=page, per_page=30, error_out=False
    )
    
    return render_template('admin/contest_submissions.html',
                         contest=contest,
                         submissions=paginated.items,
                         paginated=paginated)


@admin_bp.route('/contest/<int:contest_id>/ranklist', methods=['GET'])
@login_required
def contest_ranklist(contest_id):
    """查看竞赛排行榜"""
    _check_admin()
    
    contest = Contest.query.get_or_404(contest_id)
    ranklist = contest.get_ranklist()
    
    return render_template('admin/contest_ranklist.html',
                         contest=contest,
                         ranklist=ranklist)


# ============ 用户管理 ============

@admin_bp.route('/users', methods=['GET'])
@login_required
def users_list():
    """用户列表"""
    _check_admin()
    
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str)
    role = request.args.get('role', '', type=str)
    
    query = User.query
    
    if q:
        query = query.filter(
            db.or_(
                User.username.ilike(f'%{q}%'),
                User.email.ilike(f'%{q}%')
            )
        )
    
    if role:
        query = query.filter(User.role == role)
    
    paginated = query.paginate(page=page, per_page=20, error_out=False)
    
    return render_template('admin/users.html',
                         users=paginated.items,
                         paginated=paginated,
                         q=q,
                         role=role)


@admin_bp.route('/user/<int:user_id>/detail', methods=['GET'])
@login_required
def user_detail(user_id):
    """用户详情页"""
    _check_admin()
    
    user = User.query.get_or_404(user_id)
    
    # 统计信息
    total_submissions = Submission.query.filter_by(user_id=user_id).count()
    ac_submissions = Submission.query.filter_by(user_id=user_id, status='AC').count()
    ac_rate = (ac_submissions / total_submissions * 100) if total_submissions > 0 else 0
    
    # 语言分布
    language_dist = db.session.query(
        Submission.language,
        db.func.count(Submission.id)
    ).filter_by(user_id=user_id).group_by(Submission.language).all()
    
    # 最近提交
    recent_submissions = Submission.query.filter_by(user_id=user_id).order_by(
        Submission.submitted_at.desc()
    ).limit(20).all()
    
    # 参加的竞赛
    participated_contests = db.session.query(Contest).join(
        ContestParticipant
    ).filter(ContestParticipant.user_id == user_id).all()
    
    return render_template('admin/user_detail.html',
                         user=user,
                         total_submissions=total_submissions,
                         ac_submissions=ac_submissions,
                         ac_rate=ac_rate,
                         language_dist=language_dist,
                         recent_submissions=recent_submissions,
                         participated_contests=participated_contests)


@admin_bp.route('/user/<int:user_id>/toggle_active', methods=['POST'])
@login_required
def toggle_user_active(user_id):
    """切换用户状态"""
    _check_admin()
    
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    
    status = '已启用' if user.is_active else '已禁用'
    flash(f'用户{status}', 'success')
    return redirect(request.referrer or url_for('admin.users_list'))


@admin_bp.route('/user/<int:user_id>/toggle_role', methods=['POST'])
@login_required
def toggle_user_role(user_id):
    """切换用户角色"""
    _check_admin()
    
    if user_id == current_user.id:
        flash('不能修改自己的角色', 'error')
        return redirect(request.referrer or url_for('admin.users_list'))
    
    user = User.query.get_or_404(user_id)
    user.role = 'admin' if user.role == 'user' else 'user'
    db.session.commit()
    
    role_name = '管理员' if user.role == 'admin' else '普通用户'
    flash(f'用户角色已更改为 {role_name}', 'success')
    return redirect(request.referrer or url_for('admin.users_list'))


@admin_bp.route('/user/<int:user_id>/reset_password', methods=['POST'])
@login_required
def reset_user_password(user_id):
    """重置用户密码"""
    _check_admin()
    
    user = User.query.get_or_404(user_id)
    
    # 生成随机密码
    chars = string.ascii_letters + string.digits
    new_password = ''.join(random.choice(chars) for _ in range(8))
    
    user.set_password(new_password)
    db.session.commit()
    
    flash(f'密码已重置为：{new_password}', 'success')
    return redirect(request.referrer or url_for('admin.users_list'))


# ============ 提交和判题 ============

@admin_bp.route('/submissions', methods=['GET'])
@login_required
def submissions_list():
    """全局提交列表"""
    _check_admin()
    
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
    
    return render_template('admin/submissions.html',
                         submissions=paginated.items,
                         paginated=paginated)


@admin_bp.route('/submission/<int:submission_id>/rejudge', methods=['POST'])
@login_required
def rejudge_submission(submission_id):
    """重新判题"""
    _check_admin()
    
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


@admin_bp.route('/judge_status', methods=['GET'])
@login_required
def judge_status():
    """判题引擎状态"""
    _check_admin()
    
    # 获取引擎状态
    running = False
    worker_count = 0
    queue_size = 0
    active_tasks = 0
    
    if hasattr(current_app, 'judge_engine'):
        engine = current_app.judge_engine
        running = engine.is_running
        worker_count = engine.max_workers
    
    # 统计队列和任务
    queue_size = JudgeTask.query.filter_by(status='Queued').count()
    active_tasks = JudgeTask.query.filter(
        JudgeTask.status.in_(['Dispatched', 'Running'])
    ).count()
    
    # 获取活跃任务列表
    active_task_list = JudgeTask.query.filter(
        JudgeTask.status.in_(['Dispatched', 'Running'])
    ).order_by(JudgeTask.started_at.desc()).limit(10).all()
    
    # 获取排队任务列表
    queued_task_list = JudgeTask.query.filter_by(status='Queued').order_by(
        JudgeTask.created_at
    ).limit(10).all()
    
    # 获取最近完成的任务
    recent_tasks = JudgeTask.query.filter_by(status='Completed').order_by(
        JudgeTask.completed_at.desc()
    ).limit(10).all()
    
    return render_template('admin/judge_status.html',
                         running=running,
                         worker_count=worker_count,
                         queue_size=queue_size,
                         active_tasks=active_tasks,
                         active_task_list=active_task_list,
                         queued_task_list=queued_task_list,
                         recent_tasks=recent_tasks)
