"""Unattended start must not create an empty database and skip web setup."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

start_service = pytest.importorskip('start_service')


def test_start_service_refuses_when_the_database_is_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(start_service, 'PROJECT_ROOT', tmp_path)
    (tmp_path / '.env').write_text('SECRET_KEY=not-a-real-key-value-at-all\n', encoding='utf-8')
    monkeypatch.setattr(start_service, '_port_in_use', lambda port: False)

    def unexpected_serve(*args, **kwargs):
        raise AssertionError('must not start Waitress before first-run setup')

    monkeypatch.setitem(
        sys.modules,
        'waitress',
        type('W', (), {'serve': staticmethod(unexpected_serve)}),
    )
    assert start_service.main() == 1
    log = (tmp_path / 'data' / 'logs' / 'service.log').read_text(encoding='utf-8')
    assert '启动 EasyOJ.bat' in log
    assert not (tmp_path / 'data' / 'database.db').is_file()
