"""Write one database backup on demand, then report where it went.

Safe to run while the service is serving: ``VACUUM INTO`` produces a consistent
copy without pausing writers. Used by the deployment assistant's Back up now
button and suitable for an operator's own scheduled task.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _format_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if value < 1024 or unit == 'GB':
            return f'{value:.1f} {unit}' if unit != 'B' else f'{int(value)} B'
        value /= 1024
    return f'{value:.1f} GB'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Create an EasyOJ database backup')
    parser.add_argument('--config', default=os.environ.get('FLASK_ENV', 'production'))
    parser.add_argument('--keep', type=int, default=None, help='backups to retain')
    args = parser.parse_args(argv)

    # start_judge_engine=False: a backup must not spawn judge workers.
    from app import create_app
    from app.utils.backup import create_backup
    from app.utils.backup import list_backups

    app = create_app(args.config, start_judge_engine=False)
    database_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    backup_dir = app.config.get('BACKUP_DIR')
    keep = args.keep if args.keep is not None else app.config.get('BACKUP_KEEP', 14)

    if not backup_dir:
        print('No backup directory is configured.', file=sys.stderr)
        return 1

    result = create_backup(database_uri, backup_dir, keep=keep)
    if not result.created:
        print(f'Backup was not created: {result.reason}', file=sys.stderr)
        return 1

    print(f'Backup written: {result.path}')
    print(f'Size: {_format_size(result.size_bytes)}')
    if result.removed:
        print(f'Removed {result.removed} backup(s) beyond the retention limit of {keep}.')
    print(f'Backups on disk: {len(list_backups(backup_dir))} (keeping {keep})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
