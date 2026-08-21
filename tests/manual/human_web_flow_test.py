import json
import random
import re
import string
import threading
import time
import traceback
import urllib.parse
import urllib.request
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path

from werkzeug.serving import make_server

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = PROJECT_ROOT / 'tests' / 'reports' / 'human_web_flow'


def _setup_import_path():
    import sys

    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


_setup_import_path()

from app import create_app  # noqa: E402
from app import db  # noqa: E402
from app.models.problem import Problem  # noqa: E402
from app.utils.file_utils import ensure_dir  # noqa: E402

FINAL_STATUSES = {
    'AC',
    'WA',
    'CE',
    'RE',
    'TLE',
    'MLE',
    'Failed',
    'SystemError',
}


@dataclass
class StepResult:
    name: str
    passed: bool
    elapsed_ms: int
    detail: str


class LocalServerThread(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self._server = make_server('127.0.0.1', 0, app)
        self.port = self._server.server_port

    def run(self):
        self._server.serve_forever()

    def stop(self):
        self._server.shutdown()


def _random_suffix(length=8):
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(random.choice(alphabet) for _ in range(length))


def _write_testcases(base_dir: Path, problem_id: int):
    tc_dir = base_dir / 'data' / 'problems' / str(problem_id) / 'testcases'
    ensure_dir(str(tc_dir))
    cases = [
        ('1 2\n', '3\n'),
        ('10 20\n', '30\n'),
        ('-3 8\n', '5\n'),
    ]
    for idx, (inp, out) in enumerate(cases, start=1):
        (tc_dir / f'{idx}.in').write_text(inp, encoding='utf-8')
        (tc_dir / f'{idx}.out').write_text(out, encoding='utf-8')


def _seed_problem(app, base_dir: Path) -> int:
    with app.app_context():
        problem = Problem(
            title='Human Flow A+B',
            description='Read two integers and output their sum.',
            input_description='Two integers A and B.',
            output_description='Output A + B.',
            sample_input='1 2',
            sample_output='3',
            time_limit=1000,
            memory_limit=256,
            difficulty='easy',
            is_public=True,
        )
        db.session.add(problem)
        db.session.commit()
        problem_id = problem.id
    _write_testcases(base_dir, problem_id)
    return problem_id


def _make_http_session():
    cookies = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    opener.addheaders = [
        (
            'User-Agent',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        )
    ]
    return opener


def _request(opener, base_url: str, path: str, form_data=None):
    url = urllib.parse.urljoin(base_url, path)
    data = None
    if form_data is not None:
        data = urllib.parse.urlencode(form_data).encode('utf-8')
    req = urllib.request.Request(url=url, data=data)
    with opener.open(req, timeout=20) as resp:
        body = resp.read().decode('utf-8', errors='replace')
        return resp.getcode(), body, resp.geturl()


def _assert_contains(text: str, needle: str, context: str):
    if needle not in text:
        raise AssertionError(f"{context}: expected to find '{needle}'")


def _extract_submission_id(page_text: str) -> int:
    m = re.search(r'Submission\s*#\s*(\d+)', page_text)
    if not m:
        raise AssertionError('Submission ID not found in submission detail page')
    return int(m.group(1))


def _extract_status(page_text: str) -> str:
    m = re.search(r'<tr><th>Status</th><td><span[^>]*>([^<]+)</span>', page_text)
    if not m:
        raise AssertionError('Submission status not found in detail page')
    return m.group(1).strip()


def _run_step(step_name, fn, results):
    start = time.time()
    try:
        detail = fn()
        elapsed = int((time.time() - start) * 1000)
        results.append(StepResult(step_name, True, elapsed, detail))
        return True
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        results.append(StepResult(step_name, False, elapsed, str(exc)))
        return False


def _write_report(report: dict):
    ensure_dir(str(REPORT_DIR))
    timestamp = report['timestamp'].replace(':', '-')
    json_path = REPORT_DIR / f'report_{timestamp}.json'
    md_path = REPORT_DIR / f'report_{timestamp}.md'
    latest_json = REPORT_DIR / 'latest_report.json'
    latest_md = REPORT_DIR / 'latest_report.md'

    json_payload = json.dumps(report, ensure_ascii=False, indent=2)
    json_path.write_text(json_payload, encoding='utf-8')
    latest_json.write_text(json_payload, encoding='utf-8')

    lines = [
        '# Human Web Flow Test Report',
        '',
        f"- Timestamp: {report['timestamp']}",
        f"- Duration(ms): {report['duration_ms']}",
        f"- Overall Passed: {report['overall_passed']}",
        f"- Final Submission Status: {report.get('final_submission_status', '-')}",
        f"- Submission ID: {report.get('submission_id', '-')}",
        '',
        '## Steps',
    ]
    for step in report['steps']:
        mark = 'PASS' if step['passed'] else 'FAIL'
        lines.append(f"- [{mark}] {step['name']} | {step['elapsed_ms']} ms | {step['detail']}")

    if report.get('status_transitions'):
        lines.extend(['', '## Status Transitions'])
        for item in report['status_transitions']:
            lines.append(f"- +{item['elapsed_s']}s: {item['status']}")

    if report.get('error'):
        lines.extend(['', '## Error', '```text', report['error'], '```'])

    md_text = '\n'.join(lines) + '\n'
    md_path.write_text(md_text, encoding='utf-8')
    latest_md.write_text(md_text, encoding='utf-8')

    return json_path, md_path, latest_json, latest_md


def run_human_web_flow_test():
    started = time.time()
    results = []
    status_transitions = []
    submission_id = None
    final_status = None

    run_tag = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_base_dir = PROJECT_ROOT / 'data' / 'manual_ui_runs' / run_tag
    ensure_dir(str(run_base_dir / 'data'))
    db_path = run_base_dir / 'data' / 'database.db'
    db_uri = 'sqlite:///' + str(db_path).replace('\\', '/')

    app = create_app(
        'development',
        start_judge_engine=False,
        config_overrides={
            'DEBUG': False,
            'TESTING': False,
            'BASE_DIR': str(run_base_dir),
            'SQLALCHEMY_DATABASE_URI': db_uri,
            'MAX_JUDGE_WORKERS': 1,
        },
    )

    problem_id = _seed_problem(app, run_base_dir)
    app.judge_engine.start()
    server = LocalServerThread(app)
    server.start()
    base_url = f'http://127.0.0.1:{server.port}/'
    opener = _make_http_session()

    username = f'manual_{_random_suffix()}'
    email = f'{username}@example.com'
    password = 'password123'

    try:

        def step_visit_register():
            code, body, _ = _request(opener, base_url, 'register')
            if code != 200:
                raise AssertionError(f'GET /register returned {code}')
            _assert_contains(body, 'Register', 'Register page')
            return 'Register page is reachable'

        def step_register_user():
            code, body, final_url = _request(
                opener,
                base_url,
                'register',
                {
                    'username': username,
                    'email': email,
                    'password': password,
                    'confirm_password': password,
                },
            )
            if code != 200:
                raise AssertionError(f'POST /register returned {code}')
            _assert_contains(body, 'Registration successful', 'Register submit')
            if not final_url.endswith('/login'):
                raise AssertionError('Register did not redirect to login page')
            return f'User created: {username}'

        def step_login():
            code, body, final_url = _request(
                opener,
                base_url,
                'login',
                {
                    'username': username,
                    'password': password,
                },
            )
            if code != 200:
                raise AssertionError(f'POST /login returned {code}')
            _assert_contains(body, 'Welcome back', 'Login submit')
            if not final_url.endswith('/problems'):
                raise AssertionError(f'Login final URL unexpected: {final_url}')
            return 'Login success and redirected to problem list'

        def step_browse_problem_list():
            code, body, _ = _request(opener, base_url, 'problems')
            if code != 200:
                raise AssertionError(f'GET /problems returned {code}')
            _assert_contains(body, 'Problem Set', 'Problem list')
            _assert_contains(body, 'Human Flow A+B', 'Problem list')
            return f'Problem #{problem_id} visible in list'

        def step_open_problem_detail():
            code, body, _ = _request(opener, base_url, f'problem/{problem_id}')
            if code != 200:
                raise AssertionError(f'GET /problem/{problem_id} returned {code}')
            _assert_contains(body, 'Human Flow A+B', 'Problem detail')
            _assert_contains(body, 'Submit Code', 'Problem detail')
            return 'Problem detail page rendered'

        def step_open_submit_page():
            code, body, _ = _request(opener, base_url, f'problem/{problem_id}/submit')
            if code != 200:
                raise AssertionError(f'GET /problem/{problem_id}/submit returned {code}')
            _assert_contains(body, 'Your Code', 'Submit page')
            _assert_contains(body, 'python', 'Submit page language options')
            return 'Submit page rendered with language selector'

        def step_submit_solution():
            nonlocal submission_id
            code = (
                'import sys\n'
                'nums = list(map(int, sys.stdin.read().split()))\n'
                'print(sum(nums))\n'
            )
            status_code, body, _ = _request(
                opener,
                base_url,
                f'problem/{problem_id}/submit',
                {
                    'language': 'python',
                    'code': code,
                },
            )
            if status_code != 200:
                raise AssertionError(f'POST /problem/{problem_id}/submit returned {status_code}')
            _assert_contains(body, 'Submission #', 'Submission detail redirect')
            submission_id = _extract_submission_id(body)
            return f'Created submission #{submission_id}'

        def step_poll_submission_result():
            nonlocal final_status
            if submission_id is None:
                raise AssertionError('Submission ID missing before polling')
            poll_start = time.time()
            last_seen = None
            timeout_s = 45
            while time.time() - poll_start <= timeout_s:
                _, body, _ = _request(opener, base_url, f'submission/{submission_id}')
                status = _extract_status(body)
                if status != last_seen:
                    status_transitions.append(
                        {
                            'elapsed_s': round(time.time() - poll_start, 2),
                            'status': status,
                        }
                    )
                    last_seen = status
                if status in FINAL_STATUSES:
                    final_status = status
                    break
                time.sleep(1)
            if final_status is None:
                raise AssertionError('Polling timed out without final status')
            if final_status != 'AC':
                raise AssertionError(f'Expected AC, got {final_status}')
            return f'Final status is {final_status}'

        def step_view_submission_list():
            if submission_id is None:
                raise AssertionError('Submission ID missing')
            code, body, _ = _request(opener, base_url, 'submissions')
            if code != 200:
                raise AssertionError(f'GET /submissions returned {code}')
            _assert_contains(body, str(submission_id), 'Submission list')
            return 'Submission appears in my submissions page'

        flow_steps = [
            ('Visit register page', step_visit_register),
            ('Register new user', step_register_user),
            ('Login with new user', step_login),
            ('Browse problem list', step_browse_problem_list),
            ('Open problem detail', step_open_problem_detail),
            ('Open submit page', step_open_submit_page),
            ('Submit python solution', step_submit_solution),
            ('Poll submission result', step_poll_submission_result),
            ('Check my submissions', step_view_submission_list),
        ]

        for name, fn in flow_steps:
            ok = _run_step(name, fn, results)
            if not ok:
                break

        report = {
            'timestamp': datetime.now().isoformat(timespec='seconds'),
            'duration_ms': int((time.time() - started) * 1000),
            'overall_passed': all(item.passed for item in results),
            'steps': [asdict(item) for item in results],
            'status_transitions': status_transitions,
            'submission_id': submission_id,
            'final_submission_status': final_status,
            'run_base_dir': str(run_base_dir),
        }
    except Exception:
        report = {
            'timestamp': datetime.now().isoformat(timespec='seconds'),
            'duration_ms': int((time.time() - started) * 1000),
            'overall_passed': False,
            'steps': [asdict(item) for item in results],
            'status_transitions': status_transitions,
            'submission_id': submission_id,
            'final_submission_status': final_status,
            'run_base_dir': str(run_base_dir),
            'error': traceback.format_exc(),
        }
    finally:
        try:
            app.judge_engine.stop()
        except Exception:
            pass
        try:
            server.stop()
        except Exception:
            pass

    json_path, md_path, latest_json, latest_md = _write_report(report)

    print('Human web flow test completed.')
    print(f"Overall passed: {report['overall_passed']}")
    print(f"Final status: {report.get('final_submission_status')}")
    print(f"Submission ID: {report.get('submission_id')}")
    print(f'JSON report: {json_path}')
    print(f'Markdown report: {md_path}')
    print(f'Latest JSON report: {latest_json}')
    print(f'Latest Markdown report: {latest_md}')

    return 0 if report['overall_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(run_human_web_flow_test())
