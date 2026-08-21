import os
import sqlite3

import pytest

from app.utils.startup_maintenance import run_sqlite_migrations


def test_sqlite_migrations_are_versioned_and_idempotent(tmp_path):
    database = tmp_path / 'database.db'

    calls = []

    def migration(connection):
        calls.append(1)
        connection.execute('CREATE TABLE demo (id INTEGER PRIMARY KEY)')

    run_sqlite_migrations(str(database), [migration])
    run_sqlite_migrations(str(database), [migration])

    assert len(calls) == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT version FROM easyoj_schema_meta WHERE name = 'application'"
        ).fetchone() == (1,)


def test_sqlite_migrations_fail_closed_when_lock_is_held(tmp_path):
    database = tmp_path / 'database.db'
    lock_path = database.with_name(database.name + '.migration.lock')
    lock_path.write_text('test lock', encoding='utf-8')

    with pytest.raises(RuntimeError, match='migration lock'):
        run_sqlite_migrations(str(database), [], timeout_seconds=0.02)


def test_retention_cleanup_is_bounded_to_expected_root(tmp_path):
    from app.utils.retention import cleanup_expired_files

    root = tmp_path / 'judge_logs'
    root.mkdir()
    old_file = root / 'old.json'
    old_file.write_text('{}', encoding='utf-8')
    os.utime(old_file, (0, 0))

    result = cleanup_expired_files(root, max_age_seconds=0, max_files=1)

    assert result.removed_files == 1
    assert not old_file.exists()


def test_stale_judge_workspace_cleanup_is_bounded(tmp_path):
    from app.utils.retention import cleanup_expired_directories

    root = tmp_path / 'temp'
    root.mkdir()
    old_workspace = root / 'judge_42_123'
    old_workspace.mkdir()
    (old_workspace / 'source.cpp').write_text('int main(){}', encoding='utf-8')
    os.utime(old_workspace, (0, 0))

    result = cleanup_expired_directories(root, max_age_seconds=0, max_dirs=1)

    assert result.removed_directories == 1
    assert not old_workspace.exists()
