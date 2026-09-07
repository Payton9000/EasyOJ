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

    @property
    def display_alias(self):
        """Alias guaranteed to be non-empty.

        Aliases address problems in URLs, so legacy rows stored with NULL would
        otherwise raise BuildError and take down the whole contest page.
        """
        alias = (self.alias or '').strip()
        if alias:
            return alias
        order = self.display_order if self.display_order is not None else 0
        return chr(ord('A') + order) if 0 <= order < 26 else f'P{order}'

    __table_args__ = (
        db.UniqueConstraint('contest_id', 'problem_id', name='uq_contest_problem'),
        db.Index('idx_contest_problem_problem', 'problem_id'),
        db.Index('idx_contest_problem_contest_alias', 'contest_id', 'alias'),
    )

    def __repr__(self):
        return f'<ContestProblem {self.contest_id}-{self.problem_id}: {self.alias}>'
