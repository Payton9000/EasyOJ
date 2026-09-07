import json
from pathlib import Path

from app import db
from app.models.submission import Submission
from tests.utils import create_problem
from tests.utils import create_user


def _login(client, username, password):
    return client.post(
        '/login', data={'username': username, 'password': password}, follow_redirects=True
    )


def test_submission_detail_shows_case_trends_and_diff(client, app):
    with app.app_context():
        user = create_user('detail_case_user', 'detail_case_user@example.com')
        problem = create_problem('Detail Case Problem')

        submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            language='python',
            code='print(0)',
            status='WA',
            error_message='Wrong answer on test case 2',
            test_case_passed=1,
            test_case_total=2,
            time_used=30,
            memory_used=4096,
        )
        db.session.add(submission)
        db.session.commit()

        log_dir = Path(app.config['JUDGE_LOG_DIR'])
        log_dir.mkdir(parents=True, exist_ok=True)
        log_payload = {
            'submission_id': submission.id,
            'final_status': 'WA',
            'error': '',
            'cases': [
                {
                    'case': 1,
                    'status': 'OK',
                    'time_ms': 12,
                    'memory_kb': 2048,
                    'error': '',
                    'output_sample': '3\\n',
                },
                {
                    'case': 2,
                    'status': 'WA',
                    'time_ms': 30,
                    'memory_kb': 4096,
                    'error': '',
                    'output_sample': '4\\n',
                    'expected_sample': '5\\n',
                },
            ],
        }
        (log_dir / f'submission_{submission.id}.json').write_text(
            json.dumps(log_payload),
            encoding='utf-8',
        )

        submission_id = submission.id

    _login(client, 'detail_case_user', 'password123')

    response = client.get(f'/submission/{submission_id}')
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert 'Test Case Details' in html
    assert 'Time Trend' in html
    assert 'Memory Trend' in html
    assert 'Failed Case Diff' in html
    assert '5' in html
    assert '4' in html


def test_submission_detail_structures_compile_errors(client, app):
    with app.app_context():
        user = create_user('detail_ce_user', 'detail_ce_user@example.com')
        problem = create_problem('Detail CE Problem')

        submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            language='cpp',
            code='int main(){return ;}',
            status='CE',
            error_message="main.cpp:3:5: error: expected primary-expression before '}' token",
        )
        db.session.add(submission)
        db.session.commit()
        submission_id = submission.id

    _login(client, 'detail_ce_user', 'password123')

    response = client.get(f'/submission/{submission_id}')
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert 'Structured Compile Errors' in html
    assert 'expected primary-expression before' in html
    assert '>3<' in html
    assert '>5<' in html


def test_finished_submission_detail_does_not_auto_refresh(client, app):
    """A completed submission page must not keep reloading itself.

    A Jinja ``{% block %}`` is registered at compile time, so wrapping it in an
    ``{% if %}`` had no effect and every submission page carried the meta refresh.
    """
    with app.app_context():
        user = create_user('detail_norefresh_user', 'detail_norefresh_user@example.com')
        problem = create_problem('Detail No Refresh Problem')
        submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            language='python',
            code='print(3)',
            status='AC',
            test_case_passed=2,
            test_case_total=2,
        )
        db.session.add(submission)
        db.session.commit()
        submission_id = submission.id

    _login(client, 'detail_norefresh_user', 'password123')
    response = client.get(f'/submission/{submission_id}')

    assert response.status_code == 200
    assert 'http-equiv="refresh"' not in response.get_data(as_text=True)


def test_pending_submission_detail_still_auto_refreshes(client, app):
    with app.app_context():
        user = create_user('detail_refresh_user', 'detail_refresh_user@example.com')
        problem = create_problem('Detail Refresh Problem')
        submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            language='python',
            code='print(3)',
            status='Queued',
        )
        db.session.add(submission)
        db.session.commit()
        submission_id = submission.id

    _login(client, 'detail_refresh_user', 'password123')
    response = client.get(f'/submission/{submission_id}')

    assert response.status_code == 200
    assert 'http-equiv="refresh"' in response.get_data(as_text=True)


def test_submission_list_does_not_load_source_code(client, app):
    """The list never renders source, so 64 KB per row must not be fetched."""
    from sqlalchemy import event

    with app.app_context():
        user = create_user('defer_list_user', 'defer_list_user@example.com')
        problem = create_problem('Defer List Problem')
        for _ in range(3):
            db.session.add(
                Submission(
                    user_id=user.id,
                    problem_id=problem.id,
                    language='python',
                    code='x' * 40000,
                    status='AC',
                )
            )
        db.session.commit()

    _login(client, 'defer_list_user', 'password123')

    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', record)
    try:
        response = client.get('/submissions')
    finally:
        with app.app_context():
            event.remove(db.engine, 'before_cursor_execute', record)

    assert response.status_code == 200
    # Only the row query matters here. Pagination's count(*) wraps the full column
    # list in a subquery, but SQLite never reads columns the outer query ignores.
    row_queries = [
        s
        for s in statements
        if 'FROM submission' in s and 'count(' not in s.lower() and 'submission_id' in s
    ]
    assert row_queries, 'expected a submission row query'
    assert not any(
        'submission.code' in s for s in row_queries
    ), 'the list row query still selects the 64 KB code column'
