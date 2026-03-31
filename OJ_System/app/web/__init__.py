from flask import Blueprint

web_bp = Blueprint('web', __name__, template_folder='../templates')

from app.web import auth, problems, admin  # noqa: F401, E402
