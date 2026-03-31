from functools import wraps

from flask import Blueprint, jsonify
from flask_login import current_user

api_bp = Blueprint('api', __name__)


def api_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'code': 401, 'message': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated


from app.api import endpoints  # noqa: F401, E402
