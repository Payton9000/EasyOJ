import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.problem import Problem
from app.utils.file_utils import ensure_dir


def init_db():
    app = create_app('development')
    with app.app_context():
        db.create_all()
        print('Database tables created.')

        # Create default admin
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@oj.local', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('Admin user created (admin / admin123)')

        # Create sample problem
        if not Problem.query.filter_by(title='A+B Problem').first():
            admin_user = User.query.filter_by(username='admin').first()
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
            tc_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   'data', 'problems', str(problem.id), 'testcases')
            ensure_dir(tc_dir)
            cases = [
                ('1 2', '3'),
                ('10 20', '30'),
                ('0 0', '0'),
                ('-5 5', '0'),
                ('100 200', '300'),
            ]
            for i, (inp, out) in enumerate(cases, 1):
                with open(os.path.join(tc_dir, f'{i}.in'), 'w') as f:
                    f.write(inp + '\n')
                with open(os.path.join(tc_dir, f'{i}.out'), 'w') as f:
                    f.write(out + '\n')
            print(f'Created {len(cases)} test cases for A+B Problem')

        print('Database initialization complete.')


if __name__ == '__main__':
    init_db()
