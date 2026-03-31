from pathlib import Path
import shutil

from app import db
from app.models.problem import Problem
from app.models.user import User
from app.utils.file_utils import ensure_dir


def create_user(username='tester', email='tester@example.com', password='password123', role='user'):
    user = User(username=username, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def create_problem(title='A+B Problem', time_limit=1000, memory_limit=256):
    problem = Problem(
        title=title,
        description='Sum two integers.',
        input_description='Two integers A and B.',
        output_description='Print A+B.',
        sample_input='1 2',
        sample_output='3',
        time_limit=time_limit,
        memory_limit=memory_limit,
        difficulty='easy',
        is_public=True,
    )
    db.session.add(problem)
    db.session.commit()
    return problem


def write_testcases(base_dir, problem_id, cases):
    tc_dir = Path(base_dir) / 'data' / 'problems' / str(problem_id) / 'testcases'
    if tc_dir.exists():
        shutil.rmtree(tc_dir, ignore_errors=True)
    ensure_dir(str(tc_dir))
    for idx, (inp, out) in enumerate(cases, 1):
        (tc_dir / f'{idx}.in').write_text(inp + '\n', encoding='utf-8')
        (tc_dir / f'{idx}.out').write_text(out + '\n', encoding='utf-8')
    return tc_dir
