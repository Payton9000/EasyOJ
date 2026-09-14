"""The first-run wizard is what makes a fresh install usable.

Before it existed, setup generated a random administrator password, printed it
among thirty lines of problem-import output, and the launcher window closed eight
seconds later. That password is the only way in, so the install was effectively
bricked. These tests pin the behaviour that prevents a repeat.
"""

import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

setup_wizard = pytest.importorskip('setup_wizard')


def test_valid_choices_are_normalised():
    choices = setup_wizard.SetupChoices(
        admin_username='Teacher',
        admin_email='T@School.COM',
        admin_password='goodpass123',
        port=5099,
        site_name='  Class 3 OJ  ',
    )

    assert validate(choices, 'goodpass123') == []
    # Reuses the app's own validators, so stored values match what login expects.
    assert choices.admin_username == 'teacher'
    assert choices.admin_email == 't@school.com'
    assert choices.site_name == 'Class 3 OJ'


def validate(choices, confirm=None):
    return setup_wizard.validate_choices(choices, confirm_password=confirm)


def test_short_password_is_rejected():
    choices = setup_wizard.SetupChoices(admin_password='short')
    assert any('8 characters' in message for message in validate(choices, 'short'))


def test_mismatched_passwords_are_rejected():
    choices = setup_wizard.SetupChoices(admin_password='goodpass123')
    assert any('do not match' in message for message in validate(choices, 'goodpass124'))


def test_privileged_and_out_of_range_ports_are_rejected():
    for port in (80, 443, 1023, 70000, -1):
        choices = setup_wizard.SetupChoices(admin_password='goodpass123', port=port)
        messages = validate(choices, 'goodpass123')
        assert any('Port' in message for message in messages), f'port {port} was accepted'


def test_non_numeric_port_is_rejected():
    choices = setup_wizard.SetupChoices(admin_password='goodpass123', port='abc')
    assert any('whole number' in message for message in validate(choices, 'goodpass123'))


def test_port_already_in_use_is_rejected():
    """Accepting a busy port would leave the service unreachable after setup."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(('127.0.0.1', 0))
        holder.listen(1)
        busy = holder.getsockname()[1]

        choices = setup_wizard.SetupChoices(admin_password='goodpass123', port=busy)
        messages = validate(choices, 'goodpass123')

        assert any('already used' in message for message in messages), messages


def test_empty_site_name_is_rejected():
    choices = setup_wizard.SetupChoices(admin_password='goodpass123', site_name='   ')
    assert any('Site name' in message for message in validate(choices, 'goodpass123'))


def test_setup_wizard_does_not_import_the_flask_app():
    """System Python on first double-click has no Flask; importing app/__init__.py fails."""
    text = Path(setup_wizard.__file__).read_text(encoding='utf-8')
    assert 'from app.' not in text
    assert 'import app' not in text


def test_suggest_port_avoids_a_busy_default(monkeypatch):
    monkeypatch.setattr(setup_wizard, 'port_is_free', lambda port: port != 5000)
    assert setup_wizard.suggest_port(5000) == 5001


def test_wizard_uses_console_when_stdin_is_not_a_tty(monkeypatch):
    monkeypatch.setattr(setup_wizard.sys.stdin, 'isatty', lambda: False)
    monkeypatch.setattr(setup_wizard.sys.stdout, 'isatty', lambda: True)
    called = {}

    def fake_dialog(_choices):
        called['dialog'] = True
        raise AssertionError('dialog must not open without a TTY')

    def fake_console(choices):
        called['console'] = True
        return choices

    monkeypatch.setattr(setup_wizard, 'run_dialog', fake_dialog)
    monkeypatch.setattr(setup_wizard, 'run_console', fake_console)
    setup_wizard.run_wizard()
    assert called == {'console': True}


def test_console_flow_accepts_answers(monkeypatch):
    """Remote sessions without a desktop fall back to prompts."""
    answers = iter(
        ['teacher.li', 'li@school.example', 'Class 3 OJ', '5123', 'ClassRoom2026', 'ClassRoom2026']
    )
    monkeypatch.setattr('builtins.input', lambda _prompt='': next(answers))
    monkeypatch.setattr(setup_wizard, 'port_is_free', lambda port: True)

    result = setup_wizard.run_console(setup_wizard.SetupChoices())

    assert result.admin_username == 'teacher.li'
    assert result.admin_email == 'li@school.example'
    assert result.admin_password == 'ClassRoom2026'
    assert result.port == 5123
    assert result.site_name == 'Class 3 OJ'


def test_console_flow_cancels_cleanly(monkeypatch):
    def interrupt(_prompt=''):
        raise KeyboardInterrupt

    monkeypatch.setattr('builtins.input', interrupt)

    with pytest.raises(setup_wizard.SetupCancelled):
        setup_wizard.run_console(setup_wizard.SetupChoices())


def test_site_name_reaches_the_page_header():
    """A configured name must actually appear, not just sit in .env."""
    from app.config import Config

    assert hasattr(Config, 'SITE_NAME')
    base = (REPO_ROOT / 'app' / 'templates' / 'base.html').read_text(encoding='utf-8')
    assert "config['SITE_NAME']" in base
    # No page may hardcode the product name in its title any more.
    for template in (REPO_ROOT / 'app' / 'templates').rglob('*.html'):
        text = template.read_text(encoding='utf-8')
        assert '- EasyOJ{% endblock %}' not in text, template.name


def test_wizard_password_skips_the_forced_change_but_scripted_does_not(tmp_path, monkeypatch):
    """Only a password just typed into the wizard is exempt from a forced change.

    A password arriving purely through the environment may come from a script or
    shell history, so that installation still has to change it at first login.
    """
    import importlib

    from app import create_app
    from app import db
    from app.models.user import User

    module = importlib.import_module('init_db')

    def build(name, confirmed):
        app = create_app(
            'testing',
            start_judge_engine=False,
            config_overrides={
                'BASE_DIR': str(tmp_path / name),
                'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / (name + ".sqlite")}',
            },
        )
        with app.app_context():
            db.drop_all()
            db.create_all()
        monkeypatch.setattr(module, 'create_app', lambda *a, **k: app)
        monkeypatch.setenv('EASYOJ_INITIAL_ADMIN_PASSWORD', 'ChosenPass!2345')
        monkeypatch.setenv('EASYOJ_INITIAL_ADMIN_USERNAME', 'teacher.li')
        if confirmed:
            monkeypatch.setenv('EASYOJ_INITIAL_ADMIN_PASSWORD_CONFIRMED', '1')
        else:
            monkeypatch.delenv('EASYOJ_INITIAL_ADMIN_PASSWORD_CONFIRMED', raising=False)
        module.init_db()
        with app.app_context():
            return User.query.filter_by(username='teacher.li').one()

    assert build('wizard', confirmed=True).must_change_password is False
    assert build('scripted', confirmed=False).must_change_password is True
