from flask import jsonify, abort
from flask_login import current_user, login_required

from app.judge import judge_bp
from app import db
from app.models.judge_task import JudgeTask
from app.models.submission import Submission


def _fmt(dt):
    return dt.isoformat() if dt else None


@judge_bp.route('/status')
def judge_status():
    from flask import current_app
    engine = current_app.judge_engine
    active_tasks = JudgeTask.query.filter_by(status='Running').count()
    return jsonify({
        'running': engine.is_running,
        'worker_count': engine.max_workers,
        'queue_size': engine.task_queue.qsize(),
        'active_tasks': active_tasks,
    })


@judge_bp.route('/queue')
def judge_queue():
    tasks = JudgeTask.query.filter(
        JudgeTask.status.in_(['Queued', 'Running'])
    ).all()
    return jsonify([{
        'task_id': t.id,
        'submission_id': t.submission_id,
        'status': t.status,
        'created_at': _fmt(t.created_at),
        'started_at': _fmt(t.started_at),
        'worker_id': t.worker_id,
    } for t in tasks])


@judge_bp.route('/rejudge/<int:submission_id>', methods=['POST'])
@login_required
def judge_rejudge(submission_id):
    if not current_user.is_admin:
        abort(403)
    submission = Submission.query.get_or_404(submission_id)
    submission.status = 'Pending'

    # Delete old task if exists
    old_task = JudgeTask.query.filter_by(submission_id=submission_id).first()
    if old_task:
        db.session.delete(old_task)
        db.session.commit()

    from flask import current_app
    success = current_app.judge_engine.submit_judge_task(submission_id)
    return jsonify({'code': 0 if success else 503, 'message': 'OK' if success else 'Queue full'})
