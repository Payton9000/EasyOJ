"""Bounded LAN smoke test; it never submits judge jobs by default."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

MAX_DURATION_SECONDS = 30
MAX_USERS = 12
MAX_WORKERS = 2
MAX_REQUESTS = 100


def validate_options(duration, users, workers, max_requests):
    if not 1 <= int(duration) <= MAX_DURATION_SECONDS:
        raise ValueError(f'duration must be between 1 and {MAX_DURATION_SECONDS} seconds')
    if not 1 <= int(users) <= MAX_USERS:
        raise ValueError(f'users must be between 1 and {MAX_USERS}')
    if not 1 <= int(workers) <= MAX_WORKERS:
        raise ValueError(f'workers must be between 1 and {MAX_WORKERS}')
    if not 1 <= int(max_requests) <= MAX_REQUESTS:
        raise ValueError(f'max_requests must be between 1 and {MAX_REQUESTS}')


def run_smoke(base_url, duration=10, users=4, workers=2, max_requests=20, interval=0.1):
    validate_options(duration, users, workers, max_requests)
    if interval < 0.05 or interval > 2:
        raise ValueError('interval must be between 0.05 and 2 seconds')

    lock = threading.Lock()
    stats = {'requests': 0, 'success': 0, 'errors': 0}
    started = time.monotonic()
    deadline = started + int(duration)
    stop = threading.Event()

    def reserve_request():
        with lock:
            if stats['requests'] >= max_requests:
                stop.set()
                return False
            stats['requests'] += 1
            return True

    def worker(worker_id):
        del worker_id
        while not stop.is_set() and time.monotonic() < deadline:
            if not reserve_request():
                return
            try:
                request = urllib.request.Request(
                    base_url.rstrip('/') + '/api/problems?page=1&per_page=20',
                    headers={'Accept': 'application/json'},
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    if response.status == 200:
                        response.read(4096)
                        with lock:
                            stats['success'] += 1
                    else:
                        with lock:
                            stats['errors'] += 1
            except (OSError, urllib.error.URLError):
                with lock:
                    stats['errors'] += 1
            time.sleep(interval)

    with ThreadPoolExecutor(max_workers=int(workers), thread_name_prefix='safe-load') as pool:
        futures = [pool.submit(worker, index) for index in range(min(int(users), int(workers)))]
        for future in futures:
            future.result()

    stats['elapsed_seconds'] = round(time.monotonic() - started, 3)
    stats['pid'] = os.getpid()
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run a bounded EasyOJ LAN GET smoke test')
    parser.add_argument('--base-url', default='http://127.0.0.1:5000')
    parser.add_argument('--duration', type=int, default=10)
    parser.add_argument('--users', type=int, default=4)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--max-requests', type=int, default=20)
    parser.add_argument('--interval', type=float, default=0.1)
    args = parser.parse_args(argv)
    result = run_smoke(
        args.base_url,
        args.duration,
        args.users,
        args.workers,
        args.max_requests,
        args.interval,
    )
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result['errors'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
