from flask import redirect
from flask import session

from app.i18n import SUPPORTED_LOCALES
from app.utils.http import safe_referrer
from app.web import web_bp


@web_bp.route('/language/<locale>', methods=['POST'])
def set_language(locale):
    if locale not in SUPPORTED_LOCALES:
        return 'Unsupported language', 400
    session['locale'] = locale
    return redirect(safe_referrer('/problems'))
