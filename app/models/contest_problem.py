from app import db


class ContestProblem(db.Model):
    __tablename__ = 'contest_problem'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contest_id = db.Column(db.Integer, db.ForeignKey('contest.id'), nullable=False)
    problem_id = db.Column(db.Integer, db.ForeignKey('problem.id'), nullable=False)
    display_order = db.Column(db.Integer, default=0)  # 题目显示顺序
    alias = db.Column(db.String(5))  # 如 'A', 'B', 'C'

    # 关系
    problem = db.relationship('Problem', backref='contest_problems')

    __table_args__ = (
        db.UniqueConstraint('contest_id', 'problem_id', name='uq_contest_problem'),
    )

    def __repr__(self):
        return f'<ContestProblem {self.contest_id}-{self.problem_id}: {self.alias}>'
