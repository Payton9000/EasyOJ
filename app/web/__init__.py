from flask import Blueprint

web_bp = Blueprint('web', __name__, template_folder='../templates')

from app.web import auth  # noqa: F401, E402
from app.web import contests  # noqa: F401, E402
from app.web import locale  # noqa: F401, E402
from app.web import problems  # noqa: F401, E402
from app.web.admin import admin_bp  # noqa: F401, E402
