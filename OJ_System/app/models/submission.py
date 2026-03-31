from datetime import datetime
from app import db


class Submission(db.Model):
    __tablename__ = 'submission'
    __table_args__ = (
        db.Index('idx_user_problem', 'user_id', 'problem_id'),
        db.Index('idx_status', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    problem_id = db.Column(db.Integer, db.ForeignKey('problem.id'), nullable=False)
    language = db.Column(db.String(20), nullable=False)
    code = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default='Pending')
    time_used = db.Column(db.Integer)
    memory_used = db.Column(db.Integer)
    error_message = db.Column(db.Text)
    test_case_passed = db.Column(db.Integer, default=0)
    test_case_total = db.Column(db.Integer, default=0)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    judged_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<Submission {self.id}: user={self.user_id} problem={self.problem_id} status={self.status}>'
