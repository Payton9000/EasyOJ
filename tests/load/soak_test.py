import argparse
import json
import os
import random
import shutil
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import psutil

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import create_app  # noqa: E402
from app import db  # noqa: E402
from app.config import TestingConfig  # noqa: E402
from app.models.submission import Submission  # noqa: E402
from tests.utils import create_problem  # noqa: E402
from tests.utils import create_user  # noqa: E402
from tests.utils import write_testcases  # noqa: E402


def _login(client, username, password):
    return client.post(
        '/login', data={'username': username, 'password': password}, follow_redirects=True
    )


def _poll_submission(client, submission_id, timeout_s=10):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        res = client.get(f'/api/submission/{submission_id}')
        data = res.get_json()
        status = data['data']['status']
        if status not in ('Pending', 'Queued', 'Judging'):
            return data['data']
        time.sleep(0.1)
    return data['data']


def _cleanup_artifacts(base_dir):
    data_dir = Path(base_dir) / 'data'
    db_path = data_dir / 'soak_test.db'
    for sub in ('problems', 'submissions', 'temp'):
        shutil.rmtree(data_dir / sub, ignore_errors=True)
    if db_path.exists():
        try:
            db_path.unlink()
        except OSError:
            pass


def _build_testcases(size):
    if size == 'small':
        cases = [('1 2', '3'), ('10 20', '30')]
    elif size == 'medium':
        cases = []
        for i in range(1, 11):
            a, b = i * 7, i * 11
            cases.append((f'{a} {b}', str(a + b)))
    else:
        cases = []
        for i in range(1, 31):
            nums = [str(i + j) for j in range(10)]
            total = sum(int(x) for x in nums)
            cases.append((' '.join(nums), str(total)))
    return cases


def _scenario_pool():
    return [
        ('AC', 'python', _code_py_ac, 6),
        ('WA', 'python', _code_py_wa, 2),
        ('RE', 'python', _code_py_re, 1),
        ('TLE', 'python', _code_py_tle, 1),
        ('MLE', 'python', _code_py_mle, 1),
        ('CE', 'cpp', _code_cpp_ce, 1),
        ('AC', 'cpp', _code_cpp_ac, 4),
        ('WA', 'cpp', _code_cpp_wa, 2),
        ('TLE', 'cpp', _code_cpp_tle, 1),
        ('CE', 'java', _code_java_ce, 1),
        ('AC', 'java', _code_java_ac, 4),
        ('WA', 'java', _code_java_wa, 2),
        ('TLE', 'java', _code_java_tle, 1),
    ]


def _code_py_ac():
    return """
import sys
nums = list(map(int, sys.stdin.read().strip().split()))
if nums:
    print(sum(nums))
""".strip()


def _code_py_wa():
    return """
print(0)
""".strip()


def _code_py_re():
    return """
raise RuntimeError('boom')
""".strip()


def _code_py_tle():
    return """
while True:
    pass
""".strip()


def _code_py_mle():
    return """
data = []
while True:
    data.append(bytearray(5 * 1024 * 1024))
""".strip()


def _code_cpp_ac():
    return """
#include <bits/stdc++.h>
using namespace std;
int main(){
    long long x, sum = 0;
    while (cin >> x) sum += x;
    cout << sum;
    return 0;
}
""".strip()


def _code_cpp_wa():
    return """
#include <bits/stdc++.h>
using namespace std;
int main(){
    cout << 0;
    return 0;
}
""".strip()


def _code_cpp_tle():
    return """
int main(){
    while(true){}
    return 0;
}
""".strip()


def _code_cpp_ce():
    return """
int main(){
    return ;
}
""".strip()


def _code_java_ac():
    return """
import java.io.*;
import java.util.*;
public class Main {
    public static void main(String[] args) throws Exception {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        String line;
        long sum = 0;
        while ((line = br.readLine()) != null) {
            line = line.trim();
            if (line.isEmpty()) continue;
            for (String part : line.split("\\s+")) {
                sum += Long.parseLong(part);
            }
        }
        System.out.print(sum);
    }
}
""".strip()


def _code_java_wa():
    return """
public class Main {
    public static void main(String[] args) {
        System.out.print(0);
    }
}
""".strip()


def _code_java_tle():
    return """
public class Main {
    public static void main(String[] args) {
        while (true) {}
    }
}
""".strip()


def _code_java_ce():
    return """
public class Main {
    public static void main(String[] args) {
        System.out.println(;
    }
}
""".strip()


def _record(counter, key, amount=1):
    counter[key] = counter.get(key, 0) + amount


def _code_sample(app, submission_id, max_len=40):
    with app.app_context():
        submission = Submission.query.get(submission_id)
        if not submission or not submission.code:
            return ''
        snippet = submission.code.strip().splitlines()[0]
        return snippet[:max_len]


def _filter_scenarios(config, scenarios):
    compiler_paths = config.get('COMPILER_PATHS', {})
    filtered = []
    for scenario in scenarios:
        expected, language, code_fn, weight = scenario
        if language == 'cpp' and not os.path.isfile(compiler_paths.get('g++', '')):
            continue
        if language == 'java':
            if not os.path.isfile(compiler_paths.get('javac', '')):
                continue
            if not os.path.isfile(compiler_paths.get('java', '')):
                continue
        filtered.append(scenario)
    return filtered


def run_soak(
    duration_s=120,
    interval_s=0.5,
    report_every=10,
    users=5,
    workers=2,
    problems_per_size=2,
    poll_timeout_s=60,
):
    base_dir = BASE_DIR / 'tests'
    (base_dir / 'data').mkdir(parents=True, exist_ok=True)
    db_path = base_dir / 'data' / 'soak_test.db'
    TestingConfig.SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path}'

    app = create_app(
        'testing',
        config_overrides={
            'BASE_DIR': str(base_dir),
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        },
    )
    app.config['MAX_JUDGE_WORKERS'] = workers
    app.config['JUDGE_QUEUE_MAXSIZE'] = 200

    _cleanup_artifacts(base_dir)

    with app.app_context():
        db.drop_all()
        db.create_all()
        usernames = []
        for i in range(1, users + 1):
            user = create_user(f'soak_user_{i}', f'soak{i}@example.com')
            usernames.append(user.username)

        normal_problem_ids = []
        for size, time_limit, memory_limit in (
            ('small', 800, 128),
            ('medium', 1200, 192),
            ('large', 1500, 256),
        ):
            for idx in range(1, problems_per_size + 1):
                problem = create_problem(
                    f'Soak Sum {size} #{idx}',
                    time_limit=time_limit,
                    memory_limit=memory_limit,
                )
                write_testcases(app.config['BASE_DIR'], problem.id, _build_testcases(size))
                normal_problem_ids.append(problem.id)

        mle_problem = create_problem('Soak MLE', time_limit=1000, memory_limit=32)
        write_testcases(app.config['BASE_DIR'], mle_problem.id, _build_testcases('small'))
        mle_problem_id = mle_problem.id

    app.judge_engine.start()

    process = psutil.Process()
    start = time.time()
    last_report = start
    submissions = 0
    failures = 0
    status_counts = Counter()
    expected_counts = Counter()
    actual_counts = Counter()
    error_counts = Counter()
    worker_counts = Counter()
    mismatch_samples = []
    in_progress_counts = Counter()
    lock = threading.Lock()
    scenarios = _scenario_pool()
    scenarios = _filter_scenarios(app.config, scenarios)
    if not scenarios:
        scenarios = [
            ('AC', 'python', _code_py_ac, 6),
            ('WA', 'python', _code_py_wa, 2),
            ('RE', 'python', _code_py_re, 1),
            ('TLE', 'python', _code_py_tle, 1),
            ('MLE', 'python', _code_py_mle, 1),
        ]
    scenario_weights = [s[3] for s in scenarios]
    poll_time_total = 0.0
    poll_count = 0

    def worker_loop(username):
        nonlocal submissions, failures, poll_time_total, poll_count
        try:
            with lock:
                _record(worker_counts, 'started')
            client = app.test_client()
            _login(client, username, 'password123')

            while time.time() - start < duration_s:
                expected, language, code_fn, _ = random.choices(
                    scenarios, weights=scenario_weights, k=1
                )[0]
                if expected == 'MLE':
                    problem_id = mle_problem_id
                else:
                    problem_id = random.choice(normal_problem_ids)
                code = code_fn()

                res = client.post(
                    f'/api/submit/{problem_id}',
                    data=json.dumps({'language': language, 'code': code}),
                    content_type='application/json',
                )

                with lock:
                    submissions += 1
                    _record(expected_counts, expected)

                if res.status_code != 200:
                    with lock:
                        failures += 1
                        _record(error_counts, f'http_{res.status_code}')
                    time.sleep(interval_s)
                    continue

                submission_id = res.get_json()['data']['submission_id']
                poll_start = time.time()
                result = _poll_submission(client, submission_id, timeout_s=poll_timeout_s)
                poll_latency = time.time() - poll_start
                with lock:
                    poll_time_total += poll_latency
                    poll_count += 1
                actual = result.get('status', 'Unknown')

                with lock:
                    _record(actual_counts, actual)
                    if actual in ('Queued', 'Judging'):
                        _record(in_progress_counts, actual)
                    elif actual == expected or (
                        expected == 'MLE' and actual in ('MLE', 'RE', 'TLE')
                    ):
                        _record(status_counts, 'ok')
                    else:
                        failures += 1
                        _record(status_counts, 'mismatch')
                        _record(error_counts, f'{expected}_got_{actual}')
                        if len(mismatch_samples) < 5:
                            mismatch_samples.append(
                                {
                                    'submission_id': submission_id,
                                    'expected': expected,
                                    'actual': actual,
                                    'language': language,
                                    'code_sample': _code_sample(app, submission_id),
                                }
                            )

                time.sleep(interval_s)
        except Exception as exc:
            with lock:
                failures += 1
                _record(error_counts, f'worker_error:{type(exc).__name__}')

    try:
        with ThreadPoolExecutor(max_workers=len(usernames)) as executor:
            for username in usernames:
                executor.submit(worker_loop, username)

            while time.time() - start < duration_s:
                if time.time() - last_report >= report_every:
                    mem_mb = process.memory_info().rss / (1024 * 1024)
                    handles = getattr(process, 'num_handles', lambda: 0)()
                    cpu_pct = process.cpu_percent(interval=0.1)
                    thread_count = process.num_threads()
                    queue_size = app.judge_engine.task_queue.qsize()
                    avg_latency = (poll_time_total / poll_count) if poll_count else 0.0
                    print(
                        f'[{datetime.utcnow().isoformat()}] submissions={submissions} '
                        f'failures={failures} mem_mb={mem_mb:.2f} handles={handles} '
                        f'cpu_pct={cpu_pct:.1f} threads={thread_count} queue={queue_size} '
                        f'avg_poll_s={avg_latency:.2f}',
                        flush=True,
                    )
                    last_report = time.time()
                time.sleep(0.2)
    finally:
        app.judge_engine.stop()
        _cleanup_artifacts(base_dir)

    summary = {
        'submissions': submissions,
        'failures': failures,
        'expected': dict(expected_counts),
        'actual': dict(actual_counts),
        'mismatch': dict(error_counts),
        'workers': dict(worker_counts),
        'avg_poll_s': (poll_time_total / poll_count) if poll_count else 0.0,
        'in_progress': dict(in_progress_counts),
        'mismatch_samples': mismatch_samples,
    }
    summary_path = Path(base_dir) / 'soak_summary.json'
    try:
        summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding='utf-8')
    except OSError:
        pass
    print(f'Summary: {json.dumps(summary, ensure_ascii=True)}', flush=True)

    return submissions, failures


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=int, default=120)
    parser.add_argument('--interval', type=float, default=0.5)
    parser.add_argument('--report-every', type=int, default=10)
    parser.add_argument('--users', type=int, default=5)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--problems-per-size', type=int, default=2)
    parser.add_argument('--poll-timeout', type=int, default=60)
    args = parser.parse_args()

    total, failures = run_soak(
        args.duration,
        args.interval,
        args.report_every,
        args.users,
        args.workers,
        args.problems_per_size,
        args.poll_timeout,
    )
    print(f'Soak done. total={total} failures={failures}', flush=True)
