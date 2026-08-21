from datetime import datetime

from flask import jsonify

from app import db
from app.judge import judge_bp
from app.models.judge_task import JudgeTask
from app.models.submission import Submission
from app.services.submission_service import QUEUE_UNAVAILABLE_MESSAGE
from app.utils.decorators import admin_required


def _fmt(dt):
    return dt.isoformat() if dt else None


@judge_bp.route('/status')
@admin_required
def judge_status():
    from flask import current_app

    engine = current_app.judge_engine
    active_tasks = JudgeTask.query.filter_by(status='Running').count()
    return jsonify(
        {
            'running': engine.is_running,
            'worker_count': engine.max_workers,
            'queue_size': engine.task_queue.qsize(),
            'active_tasks': active_tasks,
        }
    )


@judge_bp.route('/queue')
@admin_required
def judge_queue():
    tasks = JudgeTask.query.filter(JudgeTask.status.in_(['Queued', 'Running'])).all()
    return jsonify(
        [
            {
                'task_id': t.id,
                'submission_id': t.submission_id,
                'status': t.status,
                'created_at': _fmt(t.created_at),
                'started_at': _fmt(t.started_at),
                'worker_id': t.worker_id,
            }
            for t in tasks
        ]
    )


@judge_bp.route('/rejudge/<int:submission_id>', methods=['POST'])
@admin_required
def judge_rejudge(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    from flask import current_app

    old_task = JudgeTask.query.filter_by(submission_id=submission_id).first()
    try:
        submission.status = 'Pending'
        if old_task:
            db.session.delete(old_task)
            db.session.flush()

        success = current_app.judge_engine.submit_judge_task(submission_id)
        if not success:
            raise RuntimeError(QUEUE_UNAVAILABLE_MESSAGE)
    except Exception:
        db.session.rollback()
        failed_submission = db.session.get(Submission, submission_id)
        retained_task = JudgeTask.query.filter_by(submission_id=submission_id).first()
        if retained_task and retained_task.status in ('Queued', 'Dispatched', 'Running'):
            retained_task.status = 'Failed'
            retained_task.completed_at = datetime.utcnow()
            retained_task.last_error = QUEUE_UNAVAILABLE_MESSAGE
        if failed_submission:
            failed_submission.status = 'Failed'
            failed_submission.error_message = QUEUE_UNAVAILABLE_MESSAGE
            db.session.commit()
        success = False
    return jsonify({'code': 0 if success else 503, 'message': 'OK' if success else 'Queue full'})
