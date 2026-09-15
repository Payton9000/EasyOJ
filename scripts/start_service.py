"""Windowless entry point used by automatic startup.

Launched by ``pythonw.exe`` from a Startup-folder shortcut or a Scheduled Task, so
there is no console to print to and no operator watching. Everything therefore
goes to a log file, and a sign-in-time start is retried: at that moment the disk
and profile may still be settling, and a single failed attempt would leave the
classroom without a judge for the rest of the day.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

LOG_RELATIVE = Path('data') / 'logs' / 'service.log'
STARTUP_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 10


def _configure_logging() -> logging.Logger:
    log_path = PROJECT_ROOT / LOG_RELATIVE
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return logging.getLogger('easyoj.service')


def _port_in_use(port: int) -> bool:
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return True
    except OSError:
        return False


def _configured_port() -> int:
    raw = os.environ.get('EASYOJ_PORT', '')
    env_file = PROJECT_ROOT / '.env'
    if not raw and env_file.is_file():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            if line.strip().startswith('EASYOJ_PORT='):
                raw = line.split('=', 1)[1].strip()
                break
    try:
        return max(1, min(65535, int(raw or 5000)))
    except ValueError:
        return 5000


def main() -> int:
    logger = _configure_logging()
    os.chdir(PROJECT_ROOT)

    port = _configured_port()
    if _port_in_use(port):
        logger.info('Port %s already serving; not starting a second instance.', port)
        return 0

    # First-run writes .env from the loopback setup page; production refuses
    # to start without it.
    if not (PROJECT_ROOT / '.env').is_file():
        logger.error(
            '.env is missing. Double-click 启动 EasyOJ.bat and finish setup in the browser.'
        )
        return 1

    if not (PROJECT_ROOT / 'data' / 'database.db').is_file():
        logger.error(
            'The database is missing. Double-click 启动 EasyOJ.bat and finish setup in the browser.'
        )
        return 1

    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / '.env', override=False)

    last_error: Exception | None = None
    for attempt in range(1, STARTUP_ATTEMPTS + 1):
        try:
            from waitress import serve

            from app import create_app

            app = create_app('production', start_judge_engine=True)
            host = os.environ.get('EASYOJ_HOST', '0.0.0.0')
            threads = max(2, min(16, os.cpu_count() or 2))
            logger.info(
                'EasyOJ starting on http://%s:%s (attempt %s, %s threads)',
                host,
                port,
                attempt,
                threads,
            )
            serve(app, host=host, port=port, threads=threads, connection_limit=256)
            return 0
        except Exception as exc:  # noqa: BLE001 - unattended launcher boundary
            last_error = exc
            logger.exception('Start attempt %s/%s failed', attempt, STARTUP_ATTEMPTS)
            if attempt < STARTUP_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)

    logger.error('Giving up after %s attempts: %s', STARTUP_ATTEMPTS, last_error)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
