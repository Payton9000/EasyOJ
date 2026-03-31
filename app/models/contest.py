from datetime import datetime
from app import db


class Contest(db.Model):
    __tablename__ = 'contest'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    is_public = db.Column(db.Boolean, default=True)
    is_sealed = db.Column(db.Boolean, default=False)
    password = db.Column(db.String(256))  # 比赛密码，可为空
    max_participants = db.Column(db.Integer, default=0)  # 0表示不限制
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 关系
    creator = db.relationship('User', backref='created_contests')
    problems = db.relationship('ContestProblem', backref='contest', lazy=True, cascade='all, delete-orphan')
    participants = db.relationship('ContestParticipant', backref='contest', lazy=True, cascade='all, delete-orphan')
    submissions = db.relationship('Submission', backref='contest', lazy=True)

    def __repr__(self):
        return f'<Contest {self.id}: {self.title}>'

    @property
    def status(self):
        """获取比赛状态: Pending | Running | Ended"""
        now = datetime.utcnow()
        if now < self.start_time:
            return 'Pending'
        elif now < self.end_time:
            return 'Running'
        else:
            return 'Ended'

    @property
    def duration(self):
        """返回比赛时长（小时）"""
        delta = self.end_time - self.start_time
        return delta.total_seconds() / 3600

    @property
    def participant_count(self):
        """返回参赛人数（不含被取消资格的）"""
        return db.session.query(db.func.count(ContestParticipant.id)).filter(
            ContestParticipant.contest_id == self.id,
            ContestParticipant.is_disqualified == False
        ).scalar() or 0

    @property
    def is_ongoing(self):
        """返回当前是否正在比赛"""
        return self.status == 'Running'

    @property
    def is_registration_open(self):
        """判断是否可以报名"""
        now = datetime.utcnow()
        if now >= self.start_time:
            return False
        if self.max_participants == 0:
            return True
        return self.participant_count < self.max_participants

    @property
    def can_submit(self):
        """判断当前是否允许提交"""
        return self.is_ongoing

    @property
    def problem_list(self):
        """返回竞赛题目列表，按display_order排序"""
        return sorted(self.problems, key=lambda x: x.display_order)

    def get_ranklist(self):
        """返回竞赛排行榜数据
        
        返回格式：
        [{
            'rank': 1,
            'user': User对象,
            'solved': 3,
            'penalty': 180,
            'problems': {contest_problem_id: {'status': 'AC'|'WA'|None, 'attempts': 2, 'ac_time': 45}}
        }, ...]
        """
        from sqlalchemy import and_
        
        # 获取所有未被取消资格的参赛者
        participants = db.session.query(ContestParticipant).filter(
            ContestParticipant.contest_id == self.id,
            ContestParticipant.is_disqualified == False
        ).all()

        if not participants:
            return []

        # 获取该竞赛的所有题目和提交
        contest_problems = db.session.query(ContestProblem).filter(
            ContestProblem.contest_id == self.id
        ).all()

        # 查询所有相关提交
        submissions = db.session.query(Submission).filter(
            Submission.contest_id == self.id
        ).all()

        ranklist = []
        for participant in participants:
            user_id = participant.user_id
            
            # 计算该用户的排名数据
            solved = 0
            total_penalty = 0
            problem_status = {}

            for cp in contest_problems:
                # 获取该用户本题的所有提交
                user_submissions = [s for s in submissions 
                                   if s.user_id == user_id and s.problem_id == cp.problem_id]
                user_submissions.sort(key=lambda x: x.submitted_at)

                status = None
                attempts = len(user_submissions)
                ac_time = None
                penalty = 0

                if user_submissions:
                    # 找第一个AC
                    ac_submission = next((s for s in user_submissions if s.status == 'AC'), None)
                    if ac_submission:
                        status = 'AC'
                        solved += 1
                        # 计算AC时间（距比赛开始的分钟数）
                        ac_time = int((ac_submission.submitted_at - self.start_time).total_seconds() / 60)
                        # 计算罚时：AC前的WA次数 * 20
                        wa_before_ac = len([s for s in user_submissions if s.submitted_at < ac_submission.submitted_at and s.status != 'AC'])
                        penalty = ac_time + wa_before_ac * 20
                        total_penalty += penalty
                    else:
                        # 没有AC，只有WA或其他
                        status = 'WA'
                        attempts = len(user_submissions)

                problem_status[cp.id] = {
                    'status': status,
                    'attempts': attempts,
                    'ac_time': ac_time,
                    'penalty': penalty
                }

            ranklist.append({
                'user': db.session.query(User).get(user_id),
                'solved': solved,
                'penalty': total_penalty,
                'problems': problem_status
            })

        # 按solved降序，再按penalty升序
        ranklist.sort(key=lambda x: (-x['solved'], x['penalty']))

        # 添加rank字段
        for idx, item in enumerate(ranklist):
            item['rank'] = idx + 1

        return ranklist

    def get_problem_status(self, user_id):
        """返回指定用户在该竞赛中每道题的状态
        
        返回格式：{contest_problem_id: {'status': 'AC'|'WA'|None, 'attempts': int, 'ac_time': int或None}}
        """
        contest_problems = db.session.query(ContestProblem).filter(
            ContestProblem.contest_id == self.id
        ).all()

        submissions = db.session.query(Submission).filter(
            Submission.contest_id == self.id,
            Submission.user_id == user_id
        ).all()

        result = {}
        for cp in contest_problems:
            user_submissions = [s for s in submissions if s.problem_id == cp.problem_id]
            user_submissions.sort(key=lambda x: x.submitted_at)

            status = None
            attempts = len(user_submissions)
            ac_time = None

            if user_submissions:
                ac_submission = next((s for s in user_submissions if s.status == 'AC'), None)
                if ac_submission:
                    status = 'AC'
                    ac_time = int((ac_submission.submitted_at - self.start_time).total_seconds() / 60)
                else:
                    status = 'WA'

            result[cp.id] = {
                'status': status,
                'attempts': attempts,
                'ac_time': ac_time
            }

        return result


from app.models.user import User
from app.models.submission import Submission
from app.models.contest_problem import ContestProblem
from app.models.contest_participant import ContestParticipant
