from datetime import datetime

from app import db


class ContestParticipant(db.Model):
    __tablename__ = 'contest_participant'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contest_id = db.Column(db.Integer, db.ForeignKey('contest.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_disqualified = db.Column(db.Boolean, default=False)

    # 关系定义在User模型中以避免backref冲突

    __table_args__ = (db.UniqueConstraint('contest_id', 'user_id', name='uq_contest_user'),)

    def __repr__(self):
        return f'<ContestParticipant {self.contest_id}-{self.user_id}>'
