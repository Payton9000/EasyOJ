from flask import request
from flask import session

from app.i18n.catalogs import CATALOGS

SUPPORTED_LOCALES = tuple(CATALOGS)
DEFAULT_LOCALE = 'en'


def get_locale():
    selected = session.get('locale')
    if selected in SUPPORTED_LOCALES:
        return selected
    return request.accept_languages.best_match(SUPPORTED_LOCALES) or DEFAULT_LOCALE


def translate(key, locale=None, **values):
    selected = locale if locale in SUPPORTED_LOCALES else get_locale()
    text = CATALOGS[selected].get(key, CATALOGS[DEFAULT_LOCALE].get(key, key))
    if not values:
        return text
    try:
        return text.format(**values)
    except (IndexError, KeyError, ValueError):
        return text


def init_i18n(app):
    @app.context_processor
    def inject_i18n():
        return {'locale': get_locale(), 't': translate}
