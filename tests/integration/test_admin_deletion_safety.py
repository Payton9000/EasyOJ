from datetime import datetime
from datetime import timedelta

from app import db
from app.models.contest import Contest
from app.models.problem import Problem
from app.models.submission import Submission
from tests.utils import create_problem
from tests.utils import create_user


def _login_admin(client, username):
    response = client.post('/login', data={'username': username, 'password': 'password123'})
    assert response.status_code == 302


def test_problem_with_submission_cannot_be_deleted(client, app):
    with app.app_context():
        admin = create_user(
            'delete_problem_admin', 'delete-problem-admin@example.com', role='admin'
        )
        student = create_user('delete_problem_student', 'delete-problem-student@example.com')
        problem = create_problem('Problem With History')
        submission = Submission(
            user_id=student.id,
            problem_id=problem.id,
            language='python',
            code='print(3)',
            status='AC',
        )
        db.session.add(submission)
        db.session.commit()
        admin_username = admin.username
        problem_id = problem.id
        submission_id = submission.id

    _login_admin(client, admin_username)
    response = client.post(
        f'/admin/problem/{problem_id}/delete',
        data={'confirmation': 'Problem With History'},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert '已有提交记录，不能删除' in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Problem, problem_id) is not None
        assert db.session.get(Submission, submission_id) is not None


def test_contest_with_submission_cannot_be_deleted(client, app):
    with app.app_context():
        admin = create_user(
            'delete_contest_admin', 'delete-contest-admin@example.com', role='admin'
        )
        student = create_user('delete_contest_student', 'delete-contest-student@example.com')
        problem = create_problem('Contest History Problem')
        now = datetime.utcnow()
        contest = Contest(
            title='Contest With History',
            start_time=now - timedelta(hours=2),
            end_time=now - timedelta(hours=1),
            is_public=True,
            created_by=admin.id,
        )
        db.session.add(contest)
        db.session.flush()
        submission = Submission(
            user_id=student.id,
            problem_id=problem.id,
            contest_id=contest.id,
            language='python',
            code='print(3)',
            status='AC',
        )
        db.session.add(submission)
        db.session.commit()
        admin_username = admin.username
        contest_id = contest.id
        submission_id = submission.id

    _login_admin(client, admin_username)
    response = client.post(
        f'/admin/contest/{contest_id}/delete',
        data={'confirmation': 'Contest With History'},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert '已有提交记录，不能删除' in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Contest, contest_id) is not None
        assert db.session.get(Submission, submission_id) is not None


def test_unused_problem_can_still_be_deleted(client, app):
    with app.app_context():
        admin = create_user('delete_unused_admin', 'delete-unused-admin@example.com', role='admin')
        problem = create_problem('Unused Deletion Problem')
        admin_username = admin.username
        problem_id = problem.id

    _login_admin(client, admin_username)
    response = client.post(
        f'/admin/problem/{problem_id}/delete',
        data={'confirmation': 'Unused Deletion Problem'},
    )

    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Problem, problem_id) is None
