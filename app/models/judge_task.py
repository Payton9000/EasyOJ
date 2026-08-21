from datetime import datetime

from app import db


class JudgeTask(db.Model):
    __tablename__ = 'judge_task'
    __table_args__ = (db.UniqueConstraint('submission_id', name='uq_judge_task_submission'),)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('submission.id'), nullable=False)
    status = db.Column(db.String(20), default='Queued')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    last_heartbeat_at = db.Column(db.DateTime)
    worker_id = db.Column(db.String(100))
    retry_count = db.Column(db.Integer, default=0)
    last_error = db.Column(db.Text)
    debug_log_path = db.Column(db.String(255))

    def __repr__(self):
        return f'<JudgeTask {self.id}: submission={self.submission_id} status={self.status}>'
