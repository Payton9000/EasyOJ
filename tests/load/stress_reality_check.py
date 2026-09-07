"""High-intensity end-to-end judge stress run against a throwaway database.

Operator-run only. This is deliberately NOT collected by pytest: it spawns real
sandboxed judge workers and executes real submissions, so it must never run as a
side effect of the normal suite. Everything lives in a scratch BASE_DIR that is
removed on exit, so the real data/ tree is never touched.

    .venv\\Scripts\\python.exe tests\\load\\stress_reality_check.py --scale small
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RESULTS: dict[str, object] = {}
FAILURES: list[str] = []
_PRINT_LOCK = threading.Lock()


def log(message: str) -> None:
    with _PRINT_LOCK:
        print(f'[{time.strftime("%H:%M:%S")}] {message}', flush=True)


def check(label: str, condition: bool, detail: str = '') -> bool:
    if condition:
        log(f'  PASS  {label}')
    else:
        FAILURES.append(f'{label}: {detail}')
        log(f'  FAIL  {label} :: {detail}')
    return condition


# Programs exercised concurrently. Each entry is (language, source, expected status).
PROGRAMS: list[tuple[str, str, str]] = [
    ('python', 'import sys\nprint(sum(int(x) for x in sys.stdin.read().split()))', 'AC'),
    ('python', 'import sys\nprint(sum(int(x) for x in sys.stdin.read().split()) + 1)', 'WA'),
    ('python', 'import sys\nwhile True: pass', 'TLE'),
    ('python', 'raise ValueError("boom")', 'RE'),
    (
        'python',
        'import sys\nprint(sum(int(x) for x in sys.stdin.read().split()))\n' + '#pad\n' * 50,
        'AC',
    ),
    (
        'cpp',
        '#include <iostream>\nint main(){long long a,b;std::cin>>a>>b;std::cout<<a+b;return 0;}',
        'AC',
    ),
    ('cpp', 'int main(){ this is not valid c++ }', 'CE'),
    (
        'cpp',
        '#include <iostream>\nint main(){long long a,b;std::cin>>a>>b;std::cout<<a+b+7;return 0;}',
        'WA',
    ),
    (
        'java',
        'import java.util.*;\npublic class Main{public static void main(String[] a){'
        'Scanner s=new Scanner(System.in);long x=s.nextLong(),y=s.nextLong();'
        'System.out.print(x+y);}}',
        'AC',
    ),
]


def build_scratch_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix='eoj_stress_'))
    for sub in ('data/problems', 'data/temp', 'data/submissions', 'data/judge_logs'):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def make_app(scratch: Path, workers: int):
    """Build an app rooted at the scratch tree with the real sandbox enabled.

    The judge engine and its policy are constructed inside ``create_app``, so
    everything it reads has to be in the environment before that call.
    """
    os.environ['JUDGE_DISPATCH_POLL_MS'] = '100'
    os.environ['MAX_JUDGE_WORKERS'] = str(workers)
    os.environ['JUDGE_WORKER_CAP'] = str(max(workers, 4))
    os.environ['JUDGE_USER_ACTIVE_MAX'] = '20'
    os.environ['JUDGE_TOTAL_ACTIVE_MAX'] = '200'
    os.environ['SUBMISSION_RATE_MAX'] = '100000'

    from app import create_app
    from app import db

    # create_app applies overrides before it builds the SQLAlchemy engine and the
    # judge engine, so the whole stack lands on the scratch tree.
    app = create_app(
        'development',
        config_overrides={
            'BASE_DIR': str(scratch),
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(scratch / 'data' / 'stress.db'),
            'JUDGE_LOG_DIR': str(scratch / 'data' / 'judge_logs'),
            'WTF_CSRF_ENABLED': False,
            'DEBUG': False,
            'MAX_JUDGE_WORKERS': workers,
            'JUDGE_WORKER_CAP': max(workers, 4),
            'JUDGE_USER_ACTIVE_MAX': 20,
            'JUDGE_TOTAL_ACTIVE_MAX': 200,
            'SUBMISSION_RATE_MAX': 100000,
        },
    )
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    if not uri.endswith('stress.db'):
        raise RuntimeError(f'refusing to run: app is bound to {uri}, not the scratch database')
    if os.path.normcase(app.config['BASE_DIR']) != os.path.normcase(str(scratch)):
        raise RuntimeError(f'refusing to run: BASE_DIR is {app.config["BASE_DIR"]}')
    with app.app_context():
        db.create_all()
    return app


def seed(app, users: int, problems: int) -> dict:
    from app import db
    from app.models.contest import Contest
    from app.models.contest_participant import ContestParticipant
    from app.models.contest_problem import ContestProblem
    from app.models.problem import Problem
    from app.models.user import User

    # ``problems`` are free for practice; ``contest_problems`` are locked by the
    # running contest, so the two sets must stay disjoint or practice submissions
    # get (correctly) rejected with 409.
    info: dict = {
        'users': [],
        'problems': [],
        'contest_problems': [],
        'contest_id': None,
        'aliases': [],
    }
    with app.app_context():
        admin = User(username='stress_admin', email='sa@example.com', role='admin')
        admin.set_password('password123')
        db.session.add(admin)
        for i in range(users):
            u = User(username=f'stress_u{i}', email=f'su{i}@example.com')
            u.set_password('password123')
            db.session.add(u)
            info['users'].append(f'stress_u{i}')
        db.session.flush()

        tc_root = Path(app.config['BASE_DIR']) / 'data' / 'problems'
        # Beyond the practice set: 3 problems for the contest, 1 for the alias
        # edge case. They must not overlap or the running-contest lock (correctly)
        # rejects practice submissions with 409.
        for i in range(problems + 4):
            p = Problem(
                title=f'Stress Sum {i}',
                description='Read two integers, print the sum.',
                input_description='Two integers.',
                output_description='Their sum.',
                sample_input='1 2',
                sample_output='3',
                time_limit=2000,
                memory_limit=256,
                difficulty='easy',
                is_public=True,
            )
            db.session.add(p)
            db.session.flush()
            if i < problems:
                info['problems'].append(p.id)
            elif len(info['contest_problems']) < 3:
                info['contest_problems'].append(p.id)
            else:
                info['alias_edge_problem'] = p.id
            tc_dir = tc_root / str(p.id) / 'testcases'
            tc_dir.mkdir(parents=True, exist_ok=True)
            for n in range(1, 4):
                a, b = n * 3, n * 7
                (tc_dir / f'{n}.in').write_text(f'{a} {b}\n', encoding='utf-8')
                (tc_dir / f'{n}.out').write_text(f'{a + b}\n', encoding='utf-8')

        now = datetime.utcnow()
        contest = Contest(
            title='Stress Contest',
            description='Concurrency check',
            start_time=now - timedelta(minutes=5),
            end_time=now + timedelta(hours=2),
            is_public=True,
            created_by=admin.id,
        )
        db.session.add(contest)
        db.session.flush()
        info['contest_id'] = contest.id
        for idx, pid in enumerate(info['contest_problems']):
            alias = chr(ord('A') + idx)
            db.session.add(
                ContestProblem(
                    contest_id=contest.id, problem_id=pid, alias=alias, display_order=idx
                )
            )
            info['aliases'].append(alias)
        for name in info['users']:
            u = User.query.filter_by(username=name).first()
            db.session.add(ContestParticipant(contest_id=contest.id, user_id=u.id))
        db.session.commit()
    return info


def login(client, username: str) -> bool:
    res = client.post(
        '/login',
        data={'username': username, 'password': 'password123'},
        follow_redirects=True,
    )
    return res.status_code == 200


def wait_for(app, submission_ids: list[int], timeout_s: float) -> dict[int, dict]:
    """Poll the database until every submission reaches a terminal state."""
    from app import db
    from app.models.submission import Submission

    pending = set(submission_ids)
    final: dict[int, dict] = {}
    deadline = time.monotonic() + timeout_s
    active = {'Pending', 'Queued', 'Judging', 'Dispatched'}
    while pending and time.monotonic() < deadline:
        with app.app_context():
            rows = Submission.query.filter(Submission.id.in_(list(pending))).all()
            for row in rows:
                if row.status not in active:
                    final[row.id] = {
                        'status': row.status,
                        'passed': row.test_case_passed,
                        'total': row.test_case_total,
                        'time_used': row.time_used,
                        'memory_used': row.memory_used,
                        'error': (row.error_message or '')[:160],
                    }
                    pending.discard(row.id)
            db.session.remove()
        if pending:
            time.sleep(0.4)
    for sid in pending:
        final[sid] = {'status': 'TIMED_OUT_WAITING', 'passed': 0, 'total': 0}
    return final


def phase_concurrent_practice(app, info, rounds: int) -> None:
    log(f'PHASE 1  concurrent practice submissions ({rounds} rounds)')
    expected: dict[int, str] = {}
    lock = threading.Lock()

    def one(idx: int):
        username = info['users'][idx % len(info['users'])]
        language, source, want = PROGRAMS[idx % len(PROGRAMS)]
        problem_id = info['problems'][idx % len(info['problems'])]
        client = app.test_client()
        if not login(client, username):
            return f'login failed for {username}'
        res = client.post(
            f'/api/submit/{problem_id}',
            json={'language': language, 'code': source},
        )
        if res.status_code != 200:
            return f'submit http {res.status_code} for {username}/{language}'
        sid = res.get_json()['data']['submission_id']
        with lock:
            expected[sid] = want
        return None

    errors = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for err in pool.map(one, range(rounds)):
            if err:
                errors.append(err)
    check('all practice submissions accepted', not errors, '; '.join(errors[:4]))

    results = wait_for(app, list(expected), timeout_s=max(120, rounds * 6))
    mismatched = [
        f'#{sid} want={want} got={results[sid]["status"]} err={results[sid].get("error", "")[:70]}'
        for sid, want in expected.items()
        if results[sid]['status'] != want
    ]
    check(
        f'{len(expected)} verdicts all match expectation',
        not mismatched,
        ' | '.join(mismatched[:6]),
    )
    RESULTS['practice_verdicts'] = dict(Counter(r['status'] for r in results.values()))

    ac = [sid for sid, want in expected.items() if want == 'AC']
    bad_counts = [
        f'#{sid} passed={results[sid]["passed"]}/{results[sid]["total"]}'
        for sid in ac
        if results[sid]['passed'] != 3 or results[sid]['total'] != 3
    ]
    check('AC submissions report passed==total==3', not bad_counts, ' | '.join(bad_counts[:5]))


def phase_contest_race(app, info, per_user: int) -> None:
    log(f'PHASE 2  contest submissions under concurrency ({per_user} per user)')
    contest_id = info['contest_id']
    errors: list[str] = []
    submission_ids: list[int] = []

    def one(username: str):
        client = app.test_client()
        if not login(client, username):
            return [f'login failed {username}']
        local_errors = []
        for k in range(per_user):
            alias = info['aliases'][k % len(info['aliases'])]
            page = client.get(f'/contest/{contest_id}/problem/{alias}')
            if page.status_code != 200:
                local_errors.append(f'{username} problem page http {page.status_code}')
                continue
            body = page.get_data(as_text=True)
            token = ''
            marker = 'name="idempotency_key" value="'
            if marker in body:
                token = body.split(marker, 1)[1].split('"', 1)[0]
            language, source, _ = PROGRAMS[k % len(PROGRAMS)]
            res = client.post(
                f'/contest/{contest_id}/submit/{alias}',
                data={'language': language, 'code': source, 'idempotency_key': token},
                follow_redirects=False,
            )
            if res.status_code not in (302, 303):
                local_errors.append(f'{username} submit http {res.status_code}')
        return local_errors

    with ThreadPoolExecutor(max_workers=6) as pool:
        for errs in pool.map(one, info['users']):
            errors.extend(errs)
    check('all contest submissions accepted', not errors, '; '.join(errors[:4]))

    from app import db
    from app.models.submission import Submission

    with app.app_context():
        submission_ids = [s.id for s in Submission.query.filter_by(contest_id=contest_id).all()]
        db.session.remove()
    expected_total = len(info['users']) * per_user
    check(
        f'contest recorded {expected_total} submissions',
        len(submission_ids) == expected_total,
        f'got {len(submission_ids)}',
    )

    results = wait_for(app, submission_ids, timeout_s=max(180, expected_total * 6))
    stuck = [sid for sid, r in results.items() if r['status'] == 'TIMED_OUT_WAITING']
    check('no contest submission stuck unjudged', not stuck, f'stuck ids: {stuck[:8]}')
    RESULTS['contest_verdicts'] = dict(Counter(r['status'] for r in results.values()))

    # Ranklist must survive concurrent scoring and stay internally consistent.
    from app.models.contest import Contest

    with app.app_context():
        contest = db.session.get(Contest, contest_id)
        ranklist = contest.get_ranklist()
        db.session.remove()
    check(
        'ranklist covers every participant',
        len(ranklist) == len(info['users']),
        f'{len(ranklist)} rows for {len(info["users"])} users',
    )
    inconsistent = [
        f'{row["user"].username}: solved={row["solved"]} but penalty={row["penalty"]}'
        for row in ranklist
        if row['solved'] == 0 and row['penalty'] != 0
    ]
    check(
        'ranklist penalty consistent with solved count',
        not inconsistent,
        ' | '.join(inconsistent[:4]),
    )


def phase_hostile_inputs(app, info) -> None:
    log('PHASE 3  hostile and edge-case submissions')
    problem_id = info['problems'][0]
    client = app.test_client()
    login(client, info['users'][0])

    cases = [
        ('empty code', {'language': 'python', 'code': ''}, 400),
        ('unknown language', {'language': 'brainfuck', 'code': 'x'}, 400),
        ('oversized code', {'language': 'python', 'code': 'x' * (70 * 1024)}, 400),
        ('code not a string', {'language': 'python', 'code': 12345}, 400),
        ('missing body keys', {}, 400),
        ('null bytes', {'language': 'python', 'code': 'print(1)\x00'}, (200, 400)),
    ]
    for label, payload, want in cases:
        res = client.post(f'/api/submit/{problem_id}', json=payload)
        ok = res.status_code in (want if isinstance(want, tuple) else (want,))
        check(f'rejects {label}', ok, f'http {res.status_code}')

    res = client.post(f'/api/submit/{problem_id}', data='not json', content_type='application/json')
    check('malformed JSON does not 500', res.status_code < 500, f'http {res.status_code}')

    # Programs that abuse the sandbox must be contained, not crash the worker.
    hostile = [
        ('fork bomb attempt', 'import os\nwhile True:\n    os.fork()'),
        ('huge stdout', 'for i in range(2000000): print("x" * 40)'),
        ('read protected file', 'print(open(r"C:\\Windows\\win.ini").read()[:20])'),
        ('spawn subprocess', 'import subprocess\nprint(subprocess.run(["cmd","/c","echo hi"]))'),
        (
            'deep recursion',
            'import sys\nsys.setrecursionlimit(10**6)\ndef f(n): return f(n+1)\nf(0)',
        ),
        ('write outside workspace', 'open(r"C:\\eoj_escape.txt","w").write("x")'),
        ('allocate huge list', 'a=[]\nwhile True: a.append(bytearray(4*1024*1024))'),
    ]
    ids = {}
    for label, source in hostile:
        res = client.post(f'/api/submit/{problem_id}', json={'language': 'python', 'code': source})
        if res.status_code == 200:
            ids[res.get_json()['data']['submission_id']] = label
        else:
            # Static screening may reject some outright; that is also acceptable.
            log(f'  note  {label} rejected before judging (http {res.status_code})')
    results = wait_for(app, list(ids), timeout_s=180)
    for sid, label in ids.items():
        status = results[sid]['status']
        contained = status in {'WA', 'TLE', 'MLE', 'OLE', 'RE', 'CE'}
        check(f'sandbox contains: {label}', contained, f'status={status}')
    RESULTS['hostile_verdicts'] = {ids[s]: results[s]['status'] for s in ids}
    check(
        'no sandbox escape wrote outside the workspace',
        not os.path.exists(r'C:\eoj_escape.txt'),
        'C:\\eoj_escape.txt exists',
    )


def phase_idempotency(app, info) -> None:
    log('PHASE 4  idempotency and duplicate handling')
    contest_id = info['contest_id']
    alias = info['aliases'][0]
    client = app.test_client()
    login(client, info['users'][1])

    page = client.get(f'/contest/{contest_id}/problem/{alias}')
    body = page.get_data(as_text=True)
    marker = 'name="idempotency_key" value="'
    token = body.split(marker, 1)[1].split('"', 1)[0] if marker in body else ''
    check('contest problem page issues an idempotency token', bool(token), 'token missing')

    from app import db
    from app.models.submission import Submission

    def count() -> int:
        with app.app_context():
            n = Submission.query.filter_by(contest_id=contest_id).count()
            db.session.remove()
        return n

    before = count()
    payload = {'language': 'python', 'code': 'print(10)', 'idempotency_key': token}
    client.post(f'/contest/{contest_id}/submit/{alias}', data=payload)
    after_first = count()
    check(
        'first submission with token is stored',
        after_first == before + 1,
        f'{before} -> {after_first}',
    )

    # Same token, same code: must be deduplicated.
    client.post(f'/contest/{contest_id}/submit/{alias}', data=payload)
    after_repeat = count()
    check(
        'identical resubmission is deduplicated',
        after_repeat == after_first,
        f'{after_first} -> {after_repeat}',
    )

    # Same token, DIFFERENT code: must NOT be silently swallowed.
    changed = {'language': 'python', 'code': 'print(999)', 'idempotency_key': token}
    client.post(f'/contest/{contest_id}/submit/{alias}', data=changed)
    after_changed = count()
    check(
        'edited code is not swallowed by a reused token',
        after_changed == after_repeat + 1,
        f'{after_repeat} -> {after_changed} (student edit would be lost)',
    )


def phase_admin_and_pages(app, info) -> None:
    log('PHASE 5  page integrity under real data')
    client = app.test_client()
    login(client, 'stress_admin')
    contest_id = info['contest_id']
    # Participant-scoped pages are checked separately as a real participant;
    # the admin is not registered so they would legitimately 403 here.
    pages = [
        '/problems',
        '/contests',
        f'/contest/{contest_id}',
        f'/contest/{contest_id}/ranklist',
        '/submissions',
        '/admin/dashboard',
        '/admin/problems',
        '/admin/contests',
        '/admin/users',
        '/admin/submissions',
        '/admin/judge_status',
        f'/admin/contest/{contest_id}/participants',
        f'/admin/contest/{contest_id}/problems',
        f'/admin/contest/{contest_id}/ranklist',
        f'/admin/contest/{contest_id}/submissions',
        '/healthz',
    ]
    broken = []
    for path in pages:
        res = client.get(path)
        if res.status_code >= 400:
            broken.append(f'{path} -> {res.status_code}')
    check('every admin and public page renders', not broken, '; '.join(broken[:6]))

    participant_client = app.test_client()
    login(participant_client, info['users'][0])
    for path in (f'/contest/{contest_id}/submissions', f'/contest/{contest_id}/ranklist'):
        res = participant_client.get(path)
        check(f'participant can open {path}', res.status_code == 200, f'http {res.status_code}')

    # A contest problem with no alias must not break the contest page. Done last,
    # in a throwaway contest, so it cannot disturb the scored contest above.
    from app import db
    from app.models.contest import Contest
    from app.models.contest_participant import ContestParticipant
    from app.models.contest_problem import ContestProblem
    from app.models.user import User

    with app.app_context():
        admin = User.query.filter_by(username='stress_admin').first()
        student = User.query.filter_by(username=info['users'][0]).first()
        now = datetime.utcnow()
        spare_contest = Contest(
            title='Alias Edge Contest',
            description='alias=None regression',
            start_time=now - timedelta(minutes=1),
            end_time=now + timedelta(hours=1),
            is_public=True,
            created_by=admin.id,
        )
        db.session.add(spare_contest)
        db.session.flush()
        db.session.add(
            ContestProblem(
                contest_id=spare_contest.id,
                problem_id=info['alias_edge_problem'],
                alias=None,
                display_order=1,
            )
        )
        db.session.add(ContestParticipant(contest_id=spare_contest.id, user_id=student.id))
        db.session.commit()
        spare_id = spare_contest.id
        db.session.remove()

    res = participant_client.get(f'/contest/{spare_id}')
    check(
        'contest page survives a problem with no alias',
        res.status_code == 200,
        f'http {res.status_code}',
    )

    # Localised status text must not leak raw machine codes to students.
    student = app.test_client()
    login(student, info['users'][0])
    body = student.get('/submissions').get_data(as_text=True)
    leaked = [code for code in ('SystemError',) if code in body]
    check('submission list does not leak raw status codes', not leaked, f'leaked {leaked}')


def phase_repeat_judging(app, info, cycles: int) -> None:
    log(f'PHASE 6  sustained judging ({cycles} sequential AC submissions)')
    client = app.test_client()
    login(client, info['users'][0])
    problem_id = info['problems'][0]
    source = 'import sys\nprint(sum(int(x) for x in sys.stdin.read().split()))'
    ids = []
    started = time.monotonic()
    for _ in range(cycles):
        res = client.post(f'/api/submit/{problem_id}', json={'language': 'python', 'code': source})
        if res.status_code == 200:
            ids.append(res.get_json()['data']['submission_id'])
        time.sleep(0.05)
    results = wait_for(app, ids, timeout_s=max(120, cycles * 6))
    elapsed = time.monotonic() - started
    verdicts = Counter(r['status'] for r in results.values())
    check(
        f'all {cycles} sustained submissions returned AC',
        verdicts.get('AC') == len(ids),
        f'{dict(verdicts)}',
    )
    RESULTS['sustained'] = {
        'count': len(ids),
        'seconds': round(elapsed, 1),
        'per_submission_s': round(elapsed / max(1, len(ids)), 2),
        'verdicts': dict(verdicts),
    }
    log(f'  {len(ids)} submissions in {elapsed:.1f}s ' f'({elapsed / max(1, len(ids)):.2f}s each)')


def phase_leak_checks(app, scratch: Path) -> None:
    log('PHASE 7  resource leak checks')
    temp_root = scratch / 'data' / 'temp'
    leftovers = [p.name for p in temp_root.iterdir()] if temp_root.is_dir() else []
    check('judge workspaces cleaned up', not leftovers, f'{len(leftovers)} left: {leftovers[:5]}')

    import psutil

    me = psutil.Process()
    children = me.children(recursive=True)
    RESULTS['child_processes'] = len(children)
    log(f'  child processes still alive: {len(children)}')

    from app import db
    from app.models.judge_task import JudgeTask

    with app.app_context():
        active = JudgeTask.query.filter(
            JudgeTask.status.in_(['Queued', 'Dispatched', 'Running'])
        ).count()
        db.session.remove()
    check('no judge task left active', active == 0, f'{active} still active')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scale', choices=('small', 'medium', 'large'), default='small')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--json-out', default='')
    args = parser.parse_args()

    profile = {
        'small': {'users': 4, 'problems': 3, 'practice': 12, 'per_user': 2, 'cycles': 8},
        'medium': {'users': 8, 'problems': 4, 'practice': 27, 'per_user': 3, 'cycles': 20},
        'large': {'users': 12, 'problems': 6, 'practice': 45, 'per_user': 4, 'cycles': 40},
    }[args.scale]

    random.seed(20260831)
    scratch = build_scratch_root()
    log(f'scratch root: {scratch}')
    log(f'scale={args.scale} profile={profile} judge_workers={args.workers}')

    app = None
    started = time.monotonic()
    try:
        app = make_app(scratch, args.workers)
        info = seed(app, profile['users'], profile['problems'])
        log(
            f'seeded {len(info["users"])} users, {len(info["problems"])} problems, '
            f'contest #{info["contest_id"]}'
        )

        engine = getattr(app, 'judge_engine', None)
        if engine is None:
            FAILURES.append('judge engine missing on app')
        else:
            # create_app already starts the engine; only start it if it is idle.
            if not engine.is_running:
                engine.start()
            check(
                f'judge engine running with {engine.max_workers} worker(s)',
                engine.is_running and len(engine.worker_processes) > 0,
                f'is_running={engine.is_running} workers={len(engine.worker_processes)}',
            )
            time.sleep(1.0)

        phase_concurrent_practice(app, info, profile['practice'])
        phase_contest_race(app, info, profile['per_user'])
        phase_hostile_inputs(app, info)
        phase_idempotency(app, info)
        phase_admin_and_pages(app, info)
        phase_repeat_judging(app, info, profile['cycles'])
        if engine is not None:
            engine.stop()
            time.sleep(0.5)
        phase_leak_checks(app, scratch)
    except Exception as exc:  # noqa: BLE001 - operator-facing harness
        import traceback

        FAILURES.append(f'harness crashed: {exc!r}')
        traceback.print_exc()
    finally:
        try:
            engine = getattr(app, 'judge_engine', None) if app else None
            if engine is not None:
                engine.stop()
        except Exception:
            pass
        shutil.rmtree(scratch, ignore_errors=True)

    total = time.monotonic() - started
    log('')
    log('=' * 68)
    log(f'RESULTS  ({total:.1f}s total)')
    for key, value in RESULTS.items():
        log(f'  {key}: {value}')
    log('')
    if FAILURES:
        log(f'FAILURES: {len(FAILURES)}')
        for item in FAILURES:
            log(f'  - {item}')
    else:
        log('ALL CHECKS PASSED')
    log('=' * 68)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({'results': RESULTS, 'failures': FAILURES}, indent=2),
            encoding='utf-8',
        )
    return 1 if FAILURES else 0


if __name__ == '__main__':
    raise SystemExit(main())
