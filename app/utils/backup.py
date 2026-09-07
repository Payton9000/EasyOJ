"""Hot SQLite backups for a single Windows LAN host.

Uses ``VACUUM INTO``, which writes a consistent copy while the judge keeps
writing, so a backup never needs the service to be stopped. Copying the file
directly would not be safe: in WAL mode the committed state is split between the
database and its -wal sidecar.

For a classroom, losing a term's submissions matters far more than a slow page,
and this is the only protection against that.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

BACKUP_PREFIX = 'easyoj-'
BACKUP_SUFFIX = '.db'
# easyoj-YYYYMMDD-HHMMSS.db, so the name alone is enough to sort and prune.
_BACKUP_PATTERN = re.compile(r'^easyoj-(\d{8})-(\d{6})\.db$')

DEFAULT_KEEP = 14
DEFAULT_MIN_INTERVAL_SECONDS = 20 * 60 * 60

# One backup at a time per process: two concurrent VACUUM INTO runs would fight
# over the same directory and could leave a half-written .partial file behind.
_BACKUP_LOCK = threading.Lock()


@dataclass(frozen=True)
class BackupResult:
    path: Path | None
    created: bool
    reason: str = ''
    removed: int = 0
    size_bytes: int = 0


def _database_path(database_uri: str) -> Path | None:
    """Extract a real file path from a SQLAlchemy SQLite URI."""
    if not database_uri.startswith('sqlite:///'):
        return None
    raw = database_uri[len('sqlite:///') :]
    if not raw or raw == ':memory:':
        return None
    return Path(raw)


def list_backups(backup_dir: str | os.PathLike[str]) -> list[Path]:
    """Return recognised backups, newest first."""
    directory = Path(backup_dir)
    if not directory.is_dir():
        return []
    found = [
        entry
        for entry in directory.iterdir()
        if entry.is_file() and _BACKUP_PATTERN.match(entry.name)
    ]
    return sorted(found, key=lambda path: path.name, reverse=True)


def latest_backup(backup_dir: str | os.PathLike[str]) -> Path | None:
    backups = list_backups(backup_dir)
    return backups[0] if backups else None


def _prune(backup_dir: Path, keep: int) -> int:
    """Delete the oldest backups beyond ``keep``. Only matching names are touched."""
    keep = max(1, int(keep))
    removed = 0
    for stale in list_backups(backup_dir)[keep:]:
        try:
            stale.unlink()
            removed += 1
        except OSError as exc:
            logger.warning('Could not remove old backup %s: %s', stale, exc)
    return removed


def create_backup(
    database_uri: str,
    backup_dir: str | os.PathLike[str],
    *,
    keep: int = DEFAULT_KEEP,
    min_interval_seconds: float | None = None,
    now: datetime | None = None,
) -> BackupResult:
    """Write one hot backup, then prune old ones.

    ``min_interval_seconds`` skips the run when a recent backup already exists,
    which is what makes it safe to call on every service start.
    """
    source = _database_path(database_uri)
    if source is None:
        return BackupResult(None, False, 'backups need a file-based SQLite database')
    if not source.is_file():
        return BackupResult(None, False, f'database file is missing: {source}')

    directory = Path(backup_dir)
    now = now or datetime.now()

    if not _BACKUP_LOCK.acquire(blocking=False):
        return BackupResult(None, False, 'another backup is already running')
    try:
        directory.mkdir(parents=True, exist_ok=True)

        if min_interval_seconds:
            newest = latest_backup(directory)
            if newest is not None:
                age = now.timestamp() - newest.stat().st_mtime
                if age < float(min_interval_seconds):
                    hours = age / 3600
                    return BackupResult(
                        newest, False, f'a backup from {hours:.1f}h ago is still recent'
                    )

        target = directory / f'{BACKUP_PREFIX}{now:%Y%m%d-%H%M%S}{BACKUP_SUFFIX}'
        # Write to .partial first so an interrupted run never leaves a file that
        # looks like a usable backup.
        staging = target.with_suffix('.partial')
        if staging.exists():
            staging.unlink()

        connection = sqlite3.connect(str(source), timeout=30)
        try:
            connection.execute('PRAGMA busy_timeout=30000')
            connection.execute('VACUUM INTO ?', (str(staging),))
        finally:
            connection.close()

        os.replace(staging, target)
        size = target.stat().st_size
        removed = _prune(directory, keep)
        logger.info('Wrote database backup %s (%d bytes)', target.name, size)
        return BackupResult(target, True, '', removed=removed, size_bytes=size)
    except (sqlite3.Error, OSError) as exc:
        logger.warning('Database backup failed: %s', exc)
        return BackupResult(None, False, str(exc))
    finally:
        _BACKUP_LOCK.release()
