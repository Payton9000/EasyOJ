from flask import Blueprint

judge_bp = Blueprint('judge', __name__)

from app.judge import routes  # noqa: F401, E402
