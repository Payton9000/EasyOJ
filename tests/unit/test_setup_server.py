"""First-run setup is a loopback web form, not Tk or console prompts."""

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

setup_server = pytest.importorskip('setup_server')


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, html
    return match.group(1)


def test_setup_server_does_not_import_the_flask_app():
    """create_app() would db.create_all() and skip first-run forever."""
    text = Path(setup_server.__file__).read_text(encoding='utf-8')
    assert 'from app import' not in text
    assert 'create_app(' not in text
    assert 'db.create_all' not in text


def test_setup_bind_host_is_loopback_only():
    assert setup_server.SETUP_BIND_HOST == '127.0.0.1'


def test_setup_page_lists_the_six_fields_and_csrf():
    captured = {}
    app = setup_server.create_setup_app(
        on_success=lambda choices: captured.setdefault('c', choices)
    )
    client = app.test_client()
    response = client.get('/setup')
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'id="setup-submit"' in body
    assert 'id="username"' in body
    assert 'id="email"' in body
    assert 'id="site_name"' in body
    assert 'id="port"' in body
    assert 'id="password"' in body
    assert 'id="confirm_password"' in body
    assert 'id="locale-toggle"' in body
    assert 'name="csrf_token"' in body


def test_setup_post_without_csrf_is_rejected():
    app = setup_server.create_setup_app(on_success=lambda _choices: None)
    client = app.test_client()
    response = client.post(
        '/setup',
        data={
            'username': 'admin',
            'email': 'admin@oj.local',
            'site_name': 'WebSetup',
            'port': '5099',
            'password': 'goodpass123',
            'confirm_password': 'goodpass123',
        },
    )
    assert response.status_code == 400


def test_setup_post_accepts_valid_choices(monkeypatch):
    monkeypatch.setattr('setup_wizard.port_is_free', lambda port: True)
    captured = {}
    app = setup_server.create_setup_app(
        on_success=lambda choices: captured.setdefault('c', choices)
    )
    client = app.test_client()
    token = _csrf(client.get('/setup').get_data(as_text=True))
    response = client.post(
        '/setup',
        data={
            'csrf_token': token,
            'username': 'Teacher.Li',
            'email': 'Li@School.example',
            'site_name': 'Class 3 OJ',
            'port': '5123',
            'password': 'ClassRoom2026',
            'confirm_password': 'ClassRoom2026',
        },
        follow_redirects=False,
    )
    assert response.status_code in {302, 303}
    choices = captured['c']
    assert choices.admin_username == 'teacher.li'
    assert choices.admin_email == 'li@school.example'
    assert choices.admin_password == 'ClassRoom2026'
    assert choices.port == 5123
    assert choices.site_name == 'Class 3 OJ'


def test_setup_post_keeps_the_form_when_passwords_differ(monkeypatch):
    monkeypatch.setattr('setup_wizard.port_is_free', lambda port: True)
    captured = {}
    app = setup_server.create_setup_app(
        on_success=lambda choices: captured.setdefault('c', choices)
    )
    client = app.test_client()
    token = _csrf(client.get('/setup').get_data(as_text=True))
    response = client.post(
        '/setup',
        data={
            'csrf_token': token,
            'username': 'admin',
            'email': 'admin@oj.local',
            'site_name': 'WebSetup',
            'port': '5099',
            'password': 'goodpass123',
            'confirm_password': 'otherpass123',
        },
    )
    assert response.status_code == 200
    assert captured == {}
    assert 'id="setup-submit"' in response.get_data(as_text=True)


def test_setup_locale_toggle_does_not_finish_setup():
    captured = {}
    app = setup_server.create_setup_app(
        on_success=lambda choices: captured.setdefault('c', choices)
    )
    client = app.test_client()
    token = _csrf(client.get('/setup').get_data(as_text=True))
    response = client.post('/setup/language', data={'csrf_token': token}, follow_redirects=True)
    body = response.get_data(as_text=True)
    assert captured == {}
    assert 'id="setup-submit"' in body
    assert '首次配置' in body or 'First-time setup' in body
