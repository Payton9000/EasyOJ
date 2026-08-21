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
