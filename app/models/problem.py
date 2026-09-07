import os
from datetime import datetime

from app import db


def _get_base_dir():
    # This module lives in app/models/, so the project root is two levels up. The
    # previous three-level fallback pointed at the drive root outside app context.
    fallback = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    try:
        from flask import current_app

        return current_app.config.get('BASE_DIR', fallback)
    except RuntimeError:
        return fallback


def _testcase_count_cache():
    """Per-request memo for testcase counts, or None outside an app context."""
    try:
        from flask import g
        from flask import has_app_context

        if not has_app_context():
            return None
        cache = getattr(g, '_easyoj_testcase_counts', None)
        if cache is None:
            cache = {}
            g._easyoj_testcase_counts = cache
        return cache
    except (RuntimeError, ImportError):
        return None


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
        # Listing a directory per access meant one syscall storm per rendered row
        # on the admin problem list, so memoise for the life of the request.
        cache = _testcase_count_cache()
        if cache is not None and self.id in cache:
            return cache[self.id]

        from app.utils.file_utils import testcase_dir

        tc_dir = testcase_dir(self.id, base_dir=_get_base_dir())
        if not os.path.isdir(tc_dir):
            count = 0
        else:
            count = sum(1 for f in os.listdir(tc_dir) if f.lower().endswith('.in'))
        if cache is not None:
            cache[self.id] = count
        return count

    def get_test_cases(self):
        """Decoded (input, expected) pairs, via the shared validated loader."""
        from app.utils.file_utils import load_test_cases

        return load_test_cases(self.id)

    def __repr__(self):
        return f'<Problem {self.id}: {self.title}>'
