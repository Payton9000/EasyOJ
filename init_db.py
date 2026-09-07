import os
import secrets
import sys

from sqlalchemy import func

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app import db
from app.models.problem import Problem
from app.models.user import User
from app.utils.file_utils import ensure_dir
from app.utils.validation import validate_email
from app.utils.validation import validate_password
from app.utils.validation import validate_username
from problem_bank.catalog import get_specs
from problem_bank.importer import import_problem_specs


def _temporary_admin_password():
    password = os.environ.get('EASYOJ_INITIAL_ADMIN_PASSWORD')
    if password is None:
        password = secrets.token_urlsafe(18)
    return validate_password(password)


def _admin_identity():
    """Administrator name/email, taken from the setup wizard when it ran.

    The wizard passes these through the environment so the operator's own chosen
    account is created instead of a fixed `admin`.
    """
    username = os.environ.get('EASYOJ_INITIAL_ADMIN_USERNAME', 'admin')
    email = os.environ.get('EASYOJ_INITIAL_ADMIN_EMAIL', 'admin@oj.local')
    try:
        username = validate_username(username)
    except ValueError:
        username = 'admin'
    try:
        email = validate_email(email)
    except ValueError:
        email = 'admin@oj.local'
    return username, email


def init_db():
    # Initialization must not start judge workers or leave child processes behind.
    builtin_specs = get_specs()
    app = create_app('development', start_judge_engine=False)
    admin_username, admin_email = _admin_identity()
    password_was_supplied = bool(os.environ.get('EASYOJ_INITIAL_ADMIN_PASSWORD'))
    # Only a password the operator typed into the wizard moments ago is exempt from
    # the forced change. A password merely passed in through the environment may
    # come from a script or shell history, so that case still forces a change.
    password_chosen_interactively = os.environ.get('EASYOJ_INITIAL_ADMIN_PASSWORD_CONFIRMED') == '1'
    with app.app_context():
        db.create_all()
        print('Database tables created.')

        # Create the first administrator.  A fixed password is unsafe even on a
        # school LAN, so a generated one is printed for the operator to save.
        admin_user = User.query.filter(func.lower(User.username) == admin_username).first()
        if not admin_user:
            admin = User(username=admin_username, email=admin_email, role='admin')
            initial_password = _temporary_admin_password()
            admin.set_password(initial_password)
            admin.must_change_password = not password_chosen_interactively
            db.session.add(admin)
            db.session.commit()
            admin_user = admin
            print(f'Admin user created: username={admin_username}')
            if not password_was_supplied:
                print(f'Temporary admin password (change at first login): {initial_password}')
        else:
            try:
                has_legacy_password = (
                    not admin_user.must_change_password and admin_user.check_password('admin123')
                )
            except ValueError:
                has_legacy_password = False
            if has_legacy_password:
                initial_password = _temporary_admin_password()
                admin_user.set_password(initial_password)
                admin_user.must_change_password = True
                db.session.commit()
                print('Legacy default admin password replaced.')
                print(f'Temporary admin password (change at first login): {initial_password}')

        # Create sample problem
        if not Problem.query.filter_by(title='A+B Problem').first():
            admin_user = (
                admin_user or User.query.filter(func.lower(User.username) == admin_username).first()
            )
            problem = Problem(
                title='A+B Problem',
                description='Calculate the sum of two integers.',
                input_description='Two integers A and B, separated by a space.',
                output_description='Print the sum A+B.',
                sample_input='1 2',
                sample_output='3',
                time_limit=1000,
                memory_limit=256,
                difficulty='easy',
                is_public=True,
                created_by=admin_user.id if admin_user else None,
            )
            db.session.add(problem)
            db.session.commit()
            print(f'Sample problem created: A+B Problem (id={problem.id})')

            # Create test cases
            tc_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'data',
                'problems',
                str(problem.id),
                'testcases',
            )
            ensure_dir(tc_dir)
            cases = [
                ('1 2', '3'),
                ('10 20', '30'),
                ('0 0', '0'),
                ('-5 5', '0'),
                ('100 200', '300'),
            ]
            for i, (inp, out) in enumerate(cases, 1):
                with open(os.path.join(tc_dir, f'{i}.in'), 'w', encoding='utf-8') as f:
                    f.write(inp + '\n')
                with open(os.path.join(tc_dir, f'{i}.out'), 'w', encoding='utf-8') as f:
                    f.write(out + '\n')
            print(f'Created {len(cases)} test cases for A+B Problem')

        summary = import_problem_specs(
            app,
            builtin_specs,
            created_by=admin_user.id if admin_user else None,
            repair_legacy=True,
        )
        print(
            'Built-in problem bank ready: '
            f'{summary.created} created, {summary.updated} updated, '
            f'{summary.repaired_problems} legacy problems repaired.'
        )

        print('Database initialization complete.')


if __name__ == '__main__':
    init_db()
