"""Import the built-in 30-problem catalog into the current local database."""

import argparse
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.models.user import User
from problem_bank.catalog import get_specs
from problem_bank.importer import import_problem_specs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--no-repair',
        action='store_true',
        help='Do not repair legacy literal backslash-n values in existing problem data.',
    )
    args = parser.parse_args()

    app = create_app('development', start_judge_engine=False)
    with app.app_context():
        admin = User.query.filter_by(role='admin', is_active=True).order_by(User.id).first()
        summary = import_problem_specs(
            app,
            get_specs(),
            created_by=admin.id if admin else None,
            repair_legacy=not args.no_repair,
        )
    print(
        'Problem bank import completed: '
        f'{summary.created} created, {summary.updated} updated, '
        f'{summary.repaired_problems} legacy problems repaired, '
        f'{summary.repaired_files} testcase files repaired.'
    )


if __name__ == '__main__':
    main()
