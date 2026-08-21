"""Small, fail-closed maintenance helpers used before worker startup."""

from __future__ import annotations

import os
import shutil
import sqlite3
import time
from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

Migration = Callable[[sqlite3.Connection], None]


def run_sqlite_migrations(
    database_path: str | os.PathLike[str],
    migrations: Iterable[Migration],
    timeout_seconds: float = 30.0,
) -> None:
    """Run numbered migrations under an exclusive, crash-visible lock.

    A leftover lock is intentionally not removed automatically: an operator can
    inspect it after a crash, and startup fails closed instead of running two
    schema writers concurrently.
    """
    database = Path(database_path).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    lock_path = database.with_name(database.name + '.migration.lock')
    deadline = time.monotonic() + max(0.01, float(timeout_seconds))
    descriptor = None

    while descriptor is None:
        try:
            descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            os.write(descriptor, f'pid={os.getpid()}\n'.encode('ascii'))
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RuntimeError(f'sqlite migration lock timeout: {lock_path}')
            time.sleep(0.05)

    try:
        connection = sqlite3.connect(
            str(database),
            timeout=max(0.1, float(timeout_seconds)),
        )
        try:
            connection.execute('PRAGMA busy_timeout=30000')
            connection.execute('BEGIN IMMEDIATE')
            connection.execute(
                'CREATE TABLE IF NOT EXISTS easyoj_schema_meta '
                '(name TEXT PRIMARY KEY, version INTEGER NOT NULL)'
            )
            row = connection.execute(
                "SELECT version FROM easyoj_schema_meta WHERE name = 'application'"
            ).fetchone()
            current_version = int(row[0]) if row else 0

            migration_list = list(migrations)
            if current_version > len(migration_list):
                raise RuntimeError(
                    f'database schema version {current_version} is newer than this application'
                )
            for version, migration in enumerate(migration_list, start=1):
                if version <= current_version:
                    continue
                migration(connection)
                if version == 1:
                    connection.execute(
                        "INSERT INTO easyoj_schema_meta(name, version) VALUES ('application', ?)",
                        (version,),
                    )
                else:
                    connection.execute(
                        "UPDATE easyoj_schema_meta SET version = ? WHERE name = 'application'",
                        (version,),
                    )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(f'sqlite schema migration failed: {exc}') from exc
        finally:
            connection.close()
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class CleanupResult:
    removed_files: int = 0
    removed_directories: int = 0
    skipped_files: int = 0


def cleanup_expired_files(
    root: str | os.PathLike[str],
    *,
    max_age_seconds: float,
    max_files: int = 100,
) -> CleanupResult:
    """Remove only old regular files directly under ``root``.

    The function never follows symlinks/reparse points, never traverses child
    directories, and has a hard per-call deletion bound.
    """
    if not root:
        return CleanupResult()
    root_path = Path(root).resolve()
    if not root_path.is_dir() or root_path.is_symlink():
        return CleanupResult()

    now = time.time()
    candidates = []
    skipped = 0
    for entry in root_path.iterdir():
        try:
            info = entry.lstat()
            if entry.is_symlink() or not entry.is_file():
                skipped += 1
                continue
            if now - info.st_mtime >= max(0.0, float(max_age_seconds)):
                candidates.append((info.st_mtime, entry))
        except OSError:
            skipped += 1

    removed = 0
    for _, entry in sorted(candidates)[: max(0, int(max_files))]:
        try:
            entry.unlink()
            removed += 1
        except OSError:
            skipped += 1
    return CleanupResult(removed_files=removed, skipped_files=skipped)


def cleanup_expired_directories(
    root: str | os.PathLike[str],
    *,
    max_age_seconds: float,
    max_dirs: int = 20,
) -> CleanupResult:
    """Remove only stale, direct child workspaces under an exact temp root."""
    if not root:
        return CleanupResult()
    root_path = Path(root).resolve()
    if not root_path.is_dir() or root_path.is_symlink():
        return CleanupResult()

    now = time.time()
    candidates = []
    skipped = 0
    for entry in root_path.iterdir():
        try:
            info = entry.lstat()
            if entry.is_symlink() or not entry.is_dir():
                skipped += 1
                continue
            if now - info.st_mtime >= max(0.0, float(max_age_seconds)):
                candidates.append((info.st_mtime, entry))
        except OSError:
            skipped += 1

    removed = 0
    for _, entry in sorted(candidates)[: max(0, int(max_dirs))]:
        try:
            shutil.rmtree(entry)
            removed += 1
        except OSError:
            skipped += 1
    return CleanupResult(removed_directories=removed, skipped_files=skipped)
