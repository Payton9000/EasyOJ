from types import SimpleNamespace

from app.judge.host_guard import HostSnapshot
from tests.utils import create_user


def _login_admin(client, app, username):
    with app.app_context():
        create_user(f'{username}_admin', f'{username}@example.com', role='admin')
    response = client.post(
        '/login',
        data={'username': f'{username}_admin', 'password': 'password123'},
        follow_redirects=True,
    )
    assert response.status_code == 200


def test_judge_status_displays_host_protection_snapshot(client, app, monkeypatch):
    _login_admin(client, app, 'judge_status_observable')

    engine = SimpleNamespace(
        is_running=True,
        max_workers=3,
        task_queue=SimpleNamespace(qsize=lambda: 7),
        host_guard=SimpleNamespace(
            snapshot=lambda: HostSnapshot(cpu_percent=42.5, available_memory_mb=2048),
            max_cpu_percent=85,
            min_available_memory_mb=1024,
        ),
        dispatch_pause_reason='host CPU usage is 90.0% (limit 85%)',
        policy=SimpleNamespace(
            max_workers=3,
            queue_maxsize=50,
            max_time_limit_ms=30000,
            max_memory_limit_mb=512,
            max_output_size=65536,
            max_processes=8,
            max_workspace_bytes=67108864,
            max_workspace_files=1024,
        ),
    )
    monkeypatch.setattr(app, 'judge_engine', engine)

    body = client.get('/admin/judge_status').get_data(as_text=True)

    assert '42.5%' in body
    assert '2048 MiB' in body
    assert 'host CPU usage is 90.0% (limit 85%)' in body
    assert '7 / 50' in body
    assert '30000 ms' in body
    assert '512 MiB' in body


def test_judge_status_shows_unavailable_when_engine_is_missing(client, app, monkeypatch):
    _login_admin(client, app, 'judge_status_unavailable')
    monkeypatch.setattr(app, 'judge_engine', None)

    response = client.get('/admin/judge_status')

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '不可用' in body


def test_judge_status_shows_unavailable_when_guard_is_missing(client, app, monkeypatch):
    _login_admin(client, app, 'judge_guard_missing')
    monkeypatch.setattr(app, 'judge_engine', SimpleNamespace(is_running=True, max_workers=1))

    response = client.get('/admin/judge_status')

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '不可用' in body
