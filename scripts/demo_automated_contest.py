"""Run a bounded, repeatable five-user contest rehearsal.

The rehearsal uses a temporary SQLite database and BASE_DIR by default.  It
exercises the browser-facing contest routes with independent Flask clients,
while the real judge engine processes the five submissions.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from concurrent.futures import as_completed
from datetime import datetime
from datetime import timedelta
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app import db
from app.models.contest import Contest
from app.models.contest_participant import ContestParticipant
from app.models.contest_problem import ContestProblem
from app.models.problem import Problem
from app.models.submission import Submission
from app.models.user import User

USER_COUNT = 5
PASSWORD = 'password123'
POLL_INTERVAL_SECONDS = 0.05
TERMINAL_STATUSES = {'AC', 'CE', 'Failed', 'MLE', 'RE', 'SystemError', 'TLE', 'WA'}


class DemoError(RuntimeError):
    """Raised when the rehearsal cannot complete its bounded contract."""


def _local_form_time(value):
    return value.astimezone().replace(tzinfo=None).strftime('%Y-%m-%dT%H:%M')


def _paths(db_path, base_dir):
    temp_dir = None
    if db_path is None and base_dir is None:
        temp_dir = tempfile.TemporaryDirectory(
            prefix='easyoj-contest-demo-',
            ignore_cleanup_errors=True,
        )
        base_dir = Path(temp_dir.name)
        db_path = base_dir / 'data' / 'database.db'
    elif base_dir is None:
        temp_dir = tempfile.TemporaryDirectory(
            prefix='easyoj-contest-demo-base-',
            ignore_cleanup_errors=True,
        )
        base_dir = Path(temp_dir.name)
    else:
        base_dir = Path(base_dir)

    base_dir = base_dir.resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    if db_path is None:
        db_path = base_dir / 'data' / 'database.db'
    db_path = Path(db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return temp_dir, db_path, base_dir


def _make_app(db_path, base_dir):
    return create_app(
        'testing',
        start_judge_engine=False,
        config_overrides={
            'BASE_DIR': str(base_dir),
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'JUDGE_LOG_DIR': str(base_dir / 'data' / 'judge_logs'),
            'MAX_JUDGE_WORKERS': 2,
            'JUDGE_QUEUE_MAXSIZE': USER_COUNT,
            'JUDGE_TOTAL_ACTIVE_MAX': USER_COUNT,
            'JUDGE_USER_ACTIVE_MAX': 1,
            'SANDBOX_ENABLED': False,
            'JUDGE_REQUIRE_SANDBOX': False,
            'SANDBOX_APP_CONTAINER': False,
            'SANDBOX_STRICT_APP_CONTAINER': False,
            'JUDGE_TIMEOUT': 5000,
            'MAX_TIME_LIMIT_MS': 5000,
            'MAX_MEMORY_LIMIT_MB': 256,
            'COMPILER_PATHS': {
                'g++': 'g++',
                'java': 'java',
                'javac': 'javac',
                'python': sys.executable,
            },
        },
    )


def _prepare_data(app, base_dir):
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(username='demo_admin', email='demo_admin@example.com', role='admin')
        admin.set_password(PASSWORD)
        db.session.add(admin)

        users = []
        for index in range(1, USER_COUNT + 1):
            user = User(
                username=f'demo_user_{index}',
                email=f'demo_user_{index}@example.com',
            )
            user.set_password(PASSWORD)
            users.append(user)
            db.session.add(user)

        problem = Problem(
            title='Automated Contest Addition',
            description='Read two integers and print their sum.',
            input_description='Two integers separated by whitespace.',
            output_description='Their sum.',
            sample_input='1 2',
            sample_output='3',
            time_limit=1000,
            memory_limit=128,
            difficulty='easy',
            is_public=True,
            created_by=admin.id,
        )
        db.session.add(problem)
        db.session.flush()

        testcase_dir = base_dir / 'data' / 'problems' / str(problem.id) / 'testcases'
        testcase_dir.mkdir(parents=True, exist_ok=True)
        (testcase_dir / '1.in').write_text('1 2\n', encoding='utf-8')
        (testcase_dir / '1.out').write_text('3\n', encoding='utf-8')
        (testcase_dir / '2.in').write_text('40 2\n', encoding='utf-8')
        (testcase_dir / '2.out').write_text('42\n', encoding='utf-8')
        db.session.commit()
        return admin.username, [user.username for user in users], problem.id


def _login(client, username):
    response = client.post(
        '/login',
        data={'username': username, 'password': PASSWORD},
        follow_redirects=False,
    )
    if response.status_code != 302:
        raise DemoError(f'login failed for {username}: HTTP {response.status_code}')


def _session_user_id(client):
    with client.session_transaction() as session:
        return session.get('_user_id')


def _create_contest_and_add_problem(app, problem_id):
    now = datetime.now().astimezone()
    start = now + timedelta(minutes=1)
    end = now + timedelta(minutes=15)
    client = app.test_client()
    _login(client, 'demo_admin')

    response = client.post(
        '/admin/contest/create',
        data={
            'title': 'Automated Contest Rehearsal',
            'description': 'Bounded five-user contest rehearsal.',
            'start_time': _local_form_time(start),
            'end_time': _local_form_time(end),
            'max_participants': USER_COUNT,
            'is_public': 'on',
        },
        follow_redirects=False,
    )
    if response.status_code != 302:
        raise DemoError(f'contest creation failed: HTTP {response.status_code}')

    match = re.search(r'/admin/contest/(\d+)/edit$', response.headers.get('Location', ''))
    if not match:
        raise DemoError('contest creation did not return an edit redirect')
    contest_id = int(match.group(1))

    response = client.post(
        f'/admin/contest/{contest_id}/problems',
        data={'problem_id': str(problem_id), 'alias': 'A'},
        follow_redirects=False,
    )
    if response.status_code != 302:
        raise DemoError(f'adding contest problem failed: HTTP {response.status_code}')

    with app.app_context():
        contest = db.session.get(Contest, contest_id)
        if contest is None or ContestProblem.query.filter_by(contest_id=contest_id).count() != 1:
            raise DemoError('contest problem setup was not persisted')
    return contest_id


def _set_contest_running(app, contest_id):
    with app.app_context():
        contest = db.session.get(Contest, contest_id)
        if contest is None:
            raise DemoError('contest disappeared before it started')
        contest.start_time = datetime.utcnow() - timedelta(seconds=1)
        contest.end_time = datetime.utcnow() + timedelta(minutes=10)
        db.session.commit()
        if contest.status != 'Running' or contest.is_registration_open:
            raise DemoError(
                'contest time transition failed: '
                f'status={contest.status!r}, '
                f'is_registration_open={contest.is_registration_open!r}, '
                f'start={contest.start_time!r}, end={contest.end_time!r}'
            )


def _registration_diagnostics(app, contest_id, usernames):
    with app.app_context():
        contest = db.session.get(Contest, contest_id)
        expected_users = User.query.filter(User.username.in_(usernames)).all()
        expected_ids = {user.id for user in expected_users}
        participants = ContestParticipant.query.filter_by(contest_id=contest_id).all()
        participant_ids = {participant.user_id for participant in participants}
        missing = sorted(
            username
            for username in usernames
            if next((user.id for user in expected_users if user.username == username), None)
            not in participant_ids
        )
        return {
            'contest_status': contest.status if contest else None,
            'is_registration_open': contest.is_registration_open if contest else None,
            'participant_count': len(participants),
            'expected_user_ids': sorted(expected_ids),
            'participant_user_ids': sorted(participant_ids),
            'missing_usernames': missing,
        }


def _assert_registrations_persisted(app, contest_id, usernames):
    diagnostics = _registration_diagnostics(app, contest_id, usernames)
    if diagnostics['missing_usernames'] or diagnostics['participant_count'] != USER_COUNT:
        raise DemoError(f'registration persistence failed: {diagnostics!r}')


def _submission_diagnostics(app, contest_id, username, session_user_id):
    with app.app_context():
        contest = db.session.get(Contest, contest_id)
        expected_user = User.query.filter_by(username=username).first()
        participant_for_session = None
        participant_for_expected = None
        if session_user_id is not None:
            participant_for_session = ContestParticipant.query.filter_by(
                contest_id=contest_id,
                user_id=int(session_user_id),
            ).first()
        if expected_user is not None:
            participant_for_expected = ContestParticipant.query.filter_by(
                contest_id=contest_id,
                user_id=expected_user.id,
            ).first()
        return {
            'session_user_id': session_user_id,
            'expected_user_id': expected_user.id if expected_user else None,
            'contest_status': contest.status if contest else None,
            'is_registration_open': contest.is_registration_open if contest else None,
            'start_time': contest.start_time.isoformat() if contest else None,
            'end_time': contest.end_time.isoformat() if contest else None,
            'participant_for_session': bool(participant_for_session),
            'participant_for_expected_user': bool(participant_for_expected),
            'participant_count': contest.participant_count if contest else None,
        }


def _register(app, contest_id, username):
    client = app.test_client()
    _login(client, username)

    response = client.post(
        f'/contest/{contest_id}/register',
        follow_redirects=False,
    )
    if response.status_code != 302:
        raise DemoError(f'registration failed for {username}: HTTP {response.status_code}')


def _submit(app, contest_id, username):
    client = app.test_client()
    _login(client, username)
    session_user_id = _session_user_id(client)
    response = client.post(
        f'/contest/{contest_id}/submit/A',
        data={
            'language': 'python',
            'code': 'a, b = map(int, input().split())\nprint(a + b)',
        },
        follow_redirects=False,
    )
    if response.status_code != 302:
        diagnostics = _submission_diagnostics(app, contest_id, username, session_user_id)
        raise DemoError(
            f'submission failed for {username}: HTTP {response.status_code}; '
            f'diagnostics={diagnostics!r}'
        )


def _wait_for_results(app, contest_id, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    while True:
        with app.app_context():
            submissions = (
                Submission.query.filter_by(contest_id=contest_id).order_by(Submission.user_id).all()
            )
            statuses = [submission.status for submission in submissions]
            if len(statuses) == USER_COUNT and all(
                status in TERMINAL_STATUSES for status in statuses
            ):
                return submissions

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DemoError(
                f'judge did not finish within {timeout_seconds}s; statuses={statuses!r}'
            )
        time.sleep(min(POLL_INTERVAL_SECONDS, remaining))


def _stop_engine(app):
    engine = app.judge_engine
    engine.stop()
    for worker in engine.workers:
        if hasattr(worker, 'terminate') and worker.is_alive():
            worker.terminate()
            worker.join(timeout=1)


def _close_app(app):
    try:
        _stop_engine(app)
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def _run_concurrently(app, contest_id, usernames, action, deadline, phase):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise DemoError(f'{phase} exceeded timeout')

    with ThreadPoolExecutor(max_workers=USER_COUNT) as pool:
        futures = [pool.submit(action, app, contest_id, username) for username in usernames]
        try:
            for future in as_completed(futures, timeout=remaining):
                future.result()
        except FuturesTimeoutError as exc:
            raise DemoError(f'{phase} exceeded timeout') from exc


def _run_demo(db_path, base_dir, timeout_seconds):
    app = None
    try:
        app = _make_app(db_path, base_dir)
        _, usernames, problem_id = _prepare_data(app, base_dir)
        contest_id = _create_contest_and_add_problem(app, problem_id)
        started_at = time.monotonic()
        deadline = started_at + timeout_seconds
        _run_concurrently(app, contest_id, usernames, _register, deadline, 'registration')
        _assert_registrations_persisted(app, contest_id, usernames)
        _set_contest_running(app, contest_id)
        app.judge_engine.start()
        _run_concurrently(app, contest_id, usernames, _submit, deadline, 'submission')
        submissions = _wait_for_results(
            app,
            contest_id,
            max(0, deadline - time.monotonic()),
        )
        statuses = [submission.status for submission in submissions]
        if statuses != ['AC'] * USER_COUNT:
            raise DemoError(f'unexpected judge results: {statuses!r}')

        with app.app_context():
            participant_count = ContestParticipant.query.filter_by(contest_id=contest_id).count()
        if participant_count != USER_COUNT:
            raise DemoError(f'expected {USER_COUNT} participants, got {participant_count}')

        return {
            'contest_id': contest_id,
            'participant_count': participant_count,
            'submission_ids': [submission.id for submission in submissions],
            'statuses': statuses,
            'elapsed_seconds': round(time.monotonic() - started_at, 3),
            'db_path': os.fspath(db_path),
            'base_dir': os.fspath(base_dir),
        }
    finally:
        if app is not None:
            _close_app(app)


def run_demo(*, db_path=None, base_dir=None, timeout_seconds=30):
    """Run the rehearsal and return its persisted outcome as a JSON-ready dict."""
    try:
        timeout_seconds = float(timeout_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError('timeout_seconds must be a positive number') from exc
    if timeout_seconds <= 0:
        raise ValueError('timeout_seconds must be a positive number')

    temp_dir, resolved_db_path, resolved_base_dir = _paths(db_path, base_dir)
    try:
        return _run_demo(resolved_db_path, resolved_base_dir, timeout_seconds)
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db-path', help='SQLite path; defaults to an isolated temporary DB')
    parser.add_argument('--base-dir', help='BASE_DIR; defaults to an isolated temporary directory')
    parser.add_argument('--timeout-seconds', type=float, default=30, help='bounded wait timeout')
    args = parser.parse_args(argv)

    try:
        result = run_demo(
            db_path=args.db_path,
            base_dir=args.base_dir,
            timeout_seconds=args.timeout_seconds,
        )
    except (DemoError, ValueError) as exc:
        parser.exit(1, f'demo failed: {exc}\n')
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
