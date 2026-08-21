from urllib.parse import urlparse

from flask import redirect
from flask import request

from app.i18n import SUPPORTED_LOCALES
from app.web import web_bp


@web_bp.route('/language/<locale>', methods=['POST'])
def set_language(locale):
    if locale not in SUPPORTED_LOCALES:
        return 'Unsupported language', 400
    from flask import session

    session['locale'] = locale
    referrer = request.referrer or ''
    parsed = urlparse(referrer)
    same_host = not parsed.netloc or parsed.netloc.casefold() == request.host.casefold()
    safe_path = parsed.path.startswith('/') and not parsed.path.startswith('//')
    if same_host and safe_path:
        target = parsed.path
        if parsed.query:
            target += '?' + parsed.query
    else:
        target = '/problems'
    return redirect(target)
