"""Backups are the only protection against losing a term of submissions."""

import sqlite3
import time
from datetime import datetime
from datetime import timedelta

from app.utils.backup import BACKUP_PREFIX
from app.utils.backup import create_backup
from app.utils.backup import latest_backup
from app.utils.backup import list_backups


def _seed_database(path, rows=200):
    connection = sqlite3.connect(str(path))
    try:
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('CREATE TABLE submission(id INTEGER PRIMARY KEY, code TEXT)')
        connection.executemany(
            'INSERT INTO submission(code) VALUES (?)', [('x' * 200,) for _ in range(rows)]
        )
        connection.commit()
    finally:
        connection.close()
    return 'sqlite:///' + str(path)


def test_backup_is_a_readable_consistent_copy(tmp_path):
    uri = _seed_database(tmp_path / 'database.db', rows=250)
    backup_dir = tmp_path / 'backups'

    result = create_backup(uri, backup_dir, keep=5)

    assert result.created is True
    assert result.path is not None
    assert result.path.name.startswith(BACKUP_PREFIX)
    assert result.size_bytes > 0
    restored = sqlite3.connect(str(result.path))
    try:
        assert restored.execute('SELECT COUNT(*) FROM submission').fetchone()[0] == 250
        assert restored.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        restored.close()


def test_backup_succeeds_while_a_write_transaction_is_open(tmp_path):
    """A backup must never require stopping the service.

    Copying the file would be unsafe in WAL mode, where committed state is split
    between the database and its -wal sidecar.
    """
    database = tmp_path / 'database.db'
    uri = _seed_database(database, rows=50)
    writer = sqlite3.connect(str(database))
    try:
        writer.execute('BEGIN')
        writer.execute("INSERT INTO submission(code) VALUES ('uncommitted')")

        result = create_backup(uri, tmp_path / 'backups', keep=5)

        assert result.created is True, result.reason
        restored = sqlite3.connect(str(result.path))
        try:
            # The in-flight row must not appear: the snapshot is of committed state.
            leaked = restored.execute(
                "SELECT COUNT(*) FROM submission WHERE code = 'uncommitted'"
            ).fetchone()[0]
            assert leaked == 0
        finally:
            restored.close()
        writer.commit()
    finally:
        writer.close()


def test_retention_keeps_only_the_newest(tmp_path):
    uri = _seed_database(tmp_path / 'database.db', rows=10)
    backup_dir = tmp_path / 'backups'

    for _ in range(4):
        create_backup(uri, backup_dir, keep=2)
        time.sleep(1.05)  # Names carry second resolution.

    kept = list_backups(backup_dir)
    assert len(kept) == 2
    assert kept == sorted(kept, key=lambda path: path.name, reverse=True)


def test_recent_backup_is_skipped_so_restarts_do_not_pile_up(tmp_path):
    uri = _seed_database(tmp_path / 'database.db', rows=10)
    backup_dir = tmp_path / 'backups'
    first = create_backup(uri, backup_dir, keep=5)
    assert first.created is True

    second = create_backup(uri, backup_dir, keep=5, min_interval_seconds=3600)

    assert second.created is False
    assert 'recent' in second.reason
    assert len(list_backups(backup_dir)) == 1


def test_due_backup_is_written_even_with_an_interval(tmp_path):
    uri = _seed_database(tmp_path / 'database.db', rows=10)
    backup_dir = tmp_path / 'backups'
    create_backup(uri, backup_dir, keep=5)

    later = create_backup(
        uri,
        backup_dir,
        keep=5,
        min_interval_seconds=60,
        now=datetime.now() + timedelta(hours=2),
    )

    assert later.created is True


def test_partial_files_are_never_left_behind(tmp_path):
    uri = _seed_database(tmp_path / 'database.db', rows=10)
    backup_dir = tmp_path / 'backups'

    create_backup(uri, backup_dir, keep=5)

    assert not any(entry.suffix == '.partial' for entry in backup_dir.iterdir())
    assert latest_backup(backup_dir) is not None


def test_missing_or_memory_database_is_reported_not_raised(tmp_path):
    absent = create_backup('sqlite:///' + str(tmp_path / 'nope.db'), tmp_path / 'b', keep=3)
    assert absent.created is False
    assert 'missing' in absent.reason

    memory = create_backup('sqlite:///:memory:', tmp_path / 'b', keep=3)
    assert memory.created is False
    assert 'file-based' in memory.reason


def test_unrelated_files_in_the_backup_directory_are_untouched(tmp_path):
    uri = _seed_database(tmp_path / 'database.db', rows=10)
    backup_dir = tmp_path / 'backups'
    backup_dir.mkdir()
    keepsake = backup_dir / 'operator-notes.txt'
    keepsake.write_text('do not delete', encoding='utf-8')

    for _ in range(3):
        create_backup(uri, backup_dir, keep=1)
        time.sleep(1.05)

    assert keepsake.is_file()
    assert len(list_backups(backup_dir)) == 1
