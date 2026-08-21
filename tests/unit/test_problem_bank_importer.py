from pathlib import Path

from app import db
from app.models.problem import Problem
from tests.utils import create_problem
from tests.utils import create_user


def _spec(title='Imported Problem'):
    from problem_bank.schema import ProblemSpec
    from problem_bank.schema import TestCase

    cases = tuple(TestCase(f'{index}\n', f'{index * 2}\n') for index in range(10))
    return ProblemSpec(
        title=title,
        difficulty='easy',
        time_limit=1000,
        memory_limit=64,
        source='test',
        description='Read an integer and double it.',
        input_description='One integer.',
        output_description='The doubled integer.',
        sample_input='1\n',
        sample_output='2\n',
        cases=cases,
    )


def test_import_is_idempotent_and_does_not_reset_users(app):
    from problem_bank.importer import import_problem_specs

    with app.app_context():
        user = create_user('catalog_admin', role='admin')
        password_hash = user.password_hash
        first = import_problem_specs(app, (_spec(),), created_by=user.id)
        second = import_problem_specs(app, (_spec(),), created_by=user.id)

        problem = Problem.query.filter_by(title='Imported Problem').one()
        assert first.created == 1
        assert first.updated == 0
        assert second.created == 0
        assert second.updated == 1
        assert len(problem.get_test_cases()) == 10
        assert problem.get_test_cases()[0] == ('0\n', '0\n')
        assert user.password_hash == password_hash


def test_legacy_repair_normalizes_db_and_testcase_text(app):
    from problem_bank.importer import repair_legacy_problem_data

    with app.app_context():
        problem = create_problem('Legacy Escaped Problem')
        problem.sample_input = r'2\n1 2'
        problem.sample_output = r'3\n'
        db.session.commit()
        testcase_dir = (
            Path(app.config['BASE_DIR']) / 'data' / 'problems' / str(problem.id) / 'testcases'
        )
        testcase_dir.mkdir(parents=True, exist_ok=True)
        (testcase_dir / '1.in').write_text(r'2\n1 2', encoding='utf-8')
        (testcase_dir / '1.out').write_text(r'3\n', encoding='utf-8')

        repaired_problems, repaired_files = repair_legacy_problem_data(
            app.config['BASE_DIR'], [problem]
        )
        db.session.commit()
        db.session.refresh(problem)

        assert repaired_problems == 1
        assert repaired_files == 2
        assert problem.sample_input == '2\n1 2'
        assert (testcase_dir / '1.in').read_text(encoding='utf-8') == '2\n1 2'
