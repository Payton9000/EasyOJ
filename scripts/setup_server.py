"""Loopback first-run form. Must not import create_app (that writes database.db)."""

from __future__ import annotations

import importlib.util
import secrets
import socket
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask_wtf.csrf import CSRFProtect
from setup_wizard import SetupCancelled
from setup_wizard import SetupChoices
from setup_wizard import suggest_port
from setup_wizard import validate_choices
from werkzeug.serving import make_server

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = Path(__file__).resolve().parent / 'setup_templates'
SETUP_BIND_HOST = '127.0.0.1'
SETUP_TIMEOUT_SECONDS = 1800


def _load_catalogs() -> dict[str, dict[str, str]]:
    path = PROJECT_ROOT / 'app' / 'i18n' / 'catalogs.py'
    spec = importlib.util.spec_from_file_location('_easyoj_setup_catalogs', path)
    if spec is None or spec.loader is None:
        raise ImportError(f'Cannot load catalogs from {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CATALOGS


def create_setup_app(*, on_success, defaults: SetupChoices | None = None):
    """Standalone Flask app: CSRF form on loopback, no SQLAlchemy."""
    catalogs = _load_catalogs()
    initial = defaults or SetupChoices(port=suggest_port())
    app = Flask(
        __name__,
        template_folder=str(TEMPLATE_DIR),
        static_folder=str(PROJECT_ROOT / 'app' / 'static'),
        static_url_path='/static',
    )
    app.secret_key = secrets.token_hex(32)
    app.config['SETUP_BIND_HOST'] = SETUP_BIND_HOST
    CSRFProtect(app)

    def current_locale() -> str:
        selected = session.get('locale')
        if selected in catalogs:
            return selected
        return 'en'

    def translate(key: str, **values: str) -> str:
        locale = current_locale()
        text = catalogs[locale].get(key, catalogs['en'].get(key, key))
        if not values:
            return text
        try:
            return text.format(**values)
        except (IndexError, KeyError, ValueError):
            return text

    @app.context_processor
    def inject_setup():
        return {'t': translate, 'locale': current_locale()}

    def form_state(choices: SetupChoices, confirm: str = '') -> dict[str, str]:
        return {
            'username': choices.admin_username,
            'email': choices.admin_email,
            'site_name': choices.site_name,
            'port': str(choices.port),
            'password': choices.admin_password,
            'confirm_password': confirm,
        }

    @app.route('/setup', methods=['GET', 'POST'])
    def setup_page():
        errors: list[str] = []
        values = form_state(initial)
        if request.method == 'POST':
            collected = SetupChoices(
                admin_username=request.form.get('username', ''),
                admin_email=request.form.get('email', ''),
                admin_password=request.form.get('password', ''),
                site_name=request.form.get('site_name', ''),
                port=request.form.get('port', ''),
            )
            confirm = request.form.get('confirm_password', '')
            values = form_state(collected, confirm)
            errors = validate_choices(collected, confirm_password=confirm)
            if not errors:
                on_success(collected)
                return redirect('/setup/done')
        return render_template('setup.html', errors=errors, values=values)

    @app.route('/setup/language', methods=['POST'])
    def setup_language():
        session['locale'] = 'zh-CN' if current_locale() == 'en' else 'en'
        return redirect('/setup')

    @app.route('/setup/done')
    def setup_done():
        return render_template('setup_done.html')

    return app


def run_setup_server(
    *, open_browser: bool = True, timeout: int = SETUP_TIMEOUT_SECONDS
) -> SetupChoices:
    """Serve /setup on 127.0.0.1 until the operator submits or the wait times out."""
    holder: dict[str, SetupChoices] = {}
    finished = threading.Event()

    def on_success(choices: SetupChoices) -> None:
        holder['choices'] = choices
        finished.set()

    app = create_setup_app(on_success=on_success)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((SETUP_BIND_HOST, 0))
        port = probe.getsockname()[1]
    server = make_server(SETUP_BIND_HOST, port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, name='EasyOJSetup', daemon=True)
    thread.start()
    url = f'http://{SETUP_BIND_HOST}:{port}/setup'
    print()
    print('Open this page on this computer to finish setup:')
    print(f'  {url}')
    print('The page is not reachable from other classroom machines.')
    print()
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    completed = finished.wait(timeout)
    if completed:
        # Keep loopback up long enough for the browser to load /setup/done.
        time.sleep(2)
    threading.Thread(target=server.shutdown, daemon=True).start()
    thread.join(timeout=5)
    if not completed or 'choices' not in holder:
        raise SetupCancelled('Setup was cancelled.')
    return holder['choices']
