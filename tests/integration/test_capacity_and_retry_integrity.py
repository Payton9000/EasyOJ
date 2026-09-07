"""Regressions for a participant cap that could be overshot and for retry state.

Both bugs were invisible in normal use: the cap only broke under concurrency, and
the stale retry fields only showed during the short re-queue window.
"""

from datetime import datetime
from datetime import timedelta

from app import db
from app.models.contest import Contest
from app.models.contest_participant import ContestParticipant
from app.models.judge_task import JudgeTask
from app.models.submission import Submission
from tests.utils import create_problem
from tests.utils import create_user


def _login(client, username, password='password123'):
    return client.post(
        '/login', data={'username': username, 'password': password}, follow_redirects=True
    )


def _pending_contest(admin_id, title, max_participants):
    now = datetime.utcnow()
    contest = Contest(
        title=title,
        description='cap test',
        start_time=now + timedelta(hours=2),
        end_time=now + timedelta(hours=4),
        is_public=True,
        max_participants=max_participants,
        created_by=admin_id,
    )
    db.session.add(contest)
    db.session.commit()
    return contest


def test_registration_cap_holds_when_the_precheck_passes(client, app, monkeypatch):
    """The cap must also be enforced after the insert.

    Under concurrency two registrations can both pass the read-only capacity check
    before either commits, and SQLite has no row locking. Forcing
    ``is_registration_open`` to True reproduces that losing interleaving
    deterministically: the row is admitted and then withdrawn if it went over.
    """
    with app.app_context():
        admin = create_user('cap_admin', 'cap_admin@example.com', role='admin')
        first_user = create_user('cap_first', 'cap_first@example.com')
        create_user('cap_second', 'cap_second@example.com')
        contest = _pending_contest(admin.id, 'Cap Contest', max_participants=1)
        db.session.add(ContestParticipant(contest_id=contest.id, user_id=first_user.id))
        db.session.commit()
        contest_id = contest.id

    # Stands in for the racing request whose pre-check ran before the first commit.
    monkeypatch.setattr(Contest, 'is_registration_open', property(lambda self: True))

    _login(client, 'cap_second')
    response = client.post(f'/contest/{contest_id}/register', follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        registered = ContestParticipant.query.filter_by(contest_id=contest_id).count()
        assert registered == 1, f'{registered} participants registered for a cap of 1'


def test_admin_add_participant_respects_the_cap(client, app):
    with app.app_context():
        admin = create_user('cap_admin2', 'cap_admin2@example.com', role='admin')
        first = create_user('cap_a', 'cap_a@example.com')
        create_user('cap_b', 'cap_b@example.com')
        contest = _pending_contest(admin.id, 'Admin Cap Contest', max_participants=1)
        db.session.add(ContestParticipant(contest_id=contest.id, user_id=first.id))
        db.session.commit()
        contest_id = contest.id

    _login(client, 'cap_admin2')
    client.post(
        f'/admin/contest/{contest_id}/participant/add',
        data={'username': 'cap_b'},
        follow_redirects=True,
    )

    with app.app_context():
        assert ContestParticipant.query.filter_by(contest_id=contest_id).count() == 1


def test_admin_add_participant_reports_an_empty_username(client, app):
    with app.app_context():
        admin = create_user('cap_admin3', 'cap_admin3@example.com', role='admin')
        contest = _pending_contest(admin.id, 'Empty Name Contest', max_participants=0)
        contest_id = contest.id

    _login(client, 'cap_admin3')
    response = client.post(
        f'/admin/contest/{contest_id}/participant/add',
        data={'username': '   '},
        follow_redirects=True,
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    # Saying "user not found" for a blank box misdiagnosed the problem.
    assert '用户不存在' not in body


def test_retry_clears_metrics_from_the_failed_attempt(app):
    """A re-queued submission must not keep the failed run's numbers.

    Only ``status`` was reset, so the detail page showed "Queued" next to a
    judged-at timestamp and a passed count produced by the attempt that failed.
    """
    with app.app_context():
        user = create_user('retry_metrics_user', 'retry_metrics_user@example.com')
        problem = create_problem('Retry Metrics Problem')
        submission = Submission(
            user_id=user.id,
            problem_id=problem.id,
            language='python',
            code='print(1)',
            status='Failed',
            time_used=1234,
            memory_used=4096,
            test_case_passed=2,
            test_case_total=5,
            judged_at=datetime.utcnow(),
            error_message='transient worker crash',
        )
        db.session.add(submission)
        db.session.flush()
        task = JudgeTask(submission_id=submission.id, status='Running', retry_count=0)
        db.session.add(task)
        db.session.commit()

        service = app.judge_engine.execution_service
        assert service.handle_task_failure(task, submission, 'boom', retryable=True) is True

        refreshed = db.session.get(Submission, submission.id)
        assert refreshed.status == 'Queued'
        assert refreshed.time_used is None
        assert refreshed.memory_used is None
        assert refreshed.test_case_passed == 0
        assert refreshed.test_case_total == 0
        assert refreshed.judged_at is None
        assert refreshed.error_message is None
