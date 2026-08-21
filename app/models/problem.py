import os
from datetime import datetime

from app import db


def _get_base_dir():
    try:
        from flask import current_app

        return current_app.config.get(
            'BASE_DIR', os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        )
    except RuntimeError:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


class Problem(db.Model):
    __tablename__ = 'problem'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    input_description = db.Column(db.Text)
    output_description = db.Column(db.Text)
    sample_input = db.Column(db.Text)
    sample_output = db.Column(db.Text)
    time_limit = db.Column(db.Integer, default=1000)
    memory_limit = db.Column(db.Integer, default=256)
    difficulty = db.Column(db.String(20), default='medium')
    source = db.Column(db.String(200))
    is_public = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))

    submissions = db.relationship('Submission', backref='problem', lazy=True)

    @property
    def test_case_count(self):
        tc_dir = os.path.join(_get_base_dir(), 'data', 'problems', str(self.id), 'testcases')
        if not os.path.isdir(tc_dir):
            return 0
        return sum(1 for f in os.listdir(tc_dir) if f.endswith('.in'))

    def get_test_cases(self):
        tc_dir = os.path.join(_get_base_dir(), 'data', 'problems', str(self.id), 'testcases')
        if not os.path.isdir(tc_dir):
            return []
        in_files = [f for f in os.listdir(tc_dir) if f.endswith('.in')]
        in_files.sort(key=lambda x: int(os.path.splitext(x)[0]))
        result = []
        for in_file in in_files:
            num = os.path.splitext(in_file)[0]
            out_file = num + '.out'
            in_path = os.path.join(tc_dir, in_file)
            out_path = os.path.join(tc_dir, out_file)
            if not os.path.isfile(out_path):
                continue
            with open(in_path, encoding='utf-8') as f:
                input_str = f.read()
            with open(out_path, encoding='utf-8') as f:
                expected_str = f.read()
            result.append((input_str, expected_str))
        return result

    def __repr__(self):
        return f'<Problem {self.id}: {self.title}>'
