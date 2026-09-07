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


def test_judge_status_task_rows_name_the_submitter_and_problem(client, app, monkeypatch):
    """Task rows must resolve the submission, not fall back to a placeholder.

    ``JudgeTask`` had no ``submission`` relationship, so the template's
    ``task.submission`` was always Undefined and both columns rendered ``?``.
    """
    from app import db
    from app.models.judge_task import JudgeTask
    from app.models.submission import Submission
    from tests.utils import create_problem

    _login_admin(client, app, 'judge_status_rows')
    with app.app_context():
        author = create_user('judge_row_author', 'judge_row_author@example.com')
        problem = create_problem('Judge Row Problem')
        submission = Submission(
            user_id=author.id,
            problem_id=problem.id,
            language='python',
            code='print(1)',
            status='Queued',
        )
        db.session.add(submission)
        db.session.flush()
        db.session.add(JudgeTask(submission_id=submission.id, status='Queued'))
        db.session.commit()

    monkeypatch.setattr(app, 'judge_engine', None)
    body = client.get('/admin/judge_status').get_data(as_text=True)

    assert 'judge_row_author' in body
    assert 'Judge Row Problem' in body
    assert '<td>?</td>' not in body
