from datetime import datetime
from datetime import timedelta

from app import db
from app.models.contest import Contest
from app.models.contest_participant import ContestParticipant
from app.models.contest_problem import ContestProblem
from app.models.submission import Submission
from tests.utils import create_problem
from tests.utils import create_user


def _login(client, username):
    return client.post('/login', data={'username': username, 'password': 'password123'})


def _create_ranked_contest(*, title, sealed, ended=False):
    admin = create_user(f'{title}_admin', f'{title}_admin@example.com', role='admin')
    user = create_user(f'{title}_student', f'{title}_student@example.com')
    now = datetime.utcnow()
    if ended:
        start_time = now - timedelta(hours=2)
        end_time = now - timedelta(hours=1)
        submitted_at = now - timedelta(hours=1, minutes=30)
    else:
        start_time = now - timedelta(hours=1)
        end_time = now + timedelta(hours=1)
        submitted_at = now - timedelta(minutes=30)

    contest = Contest(
        title=title,
        start_time=start_time,
        end_time=end_time,
        is_public=True,
        is_sealed=sealed,
        created_by=admin.id,
    )
    db.session.add(contest)
    db.session.flush()
    problem = create_problem(f'{title} Problem')
    db.session.add(
        ContestProblem(
            contest_id=contest.id,
            problem_id=problem.id,
            alias='A',
            display_order=1,
        )
    )
    db.session.add(ContestParticipant(contest_id=contest.id, user_id=user.id))
    db.session.add(
        Submission(
            user_id=user.id,
            problem_id=problem.id,
            contest_id=contest.id,
            language='python',
            code='print(3)',
            status='AC',
            submitted_at=submitted_at,
        )
    )
    db.session.commit()
    return contest.id, admin.username, user.username


def test_running_sealed_ranklist_hides_rows_from_public_and_participants(client, app):
    with app.app_context():
        contest_id, _, username = _create_ranked_contest(
            title='sealed_live',
            sealed=True,
        )

    anonymous = client.get(f'/contest/{contest_id}/ranklist')
    assert anonymous.status_code == 200
    assert 'Ranklist is sealed until the contest ends.' in anonymous.get_data(as_text=True)
    assert f'<td>{username}</td>' not in anonymous.get_data(as_text=True)

    _login(client, username)
    participant = client.get(f'/contest/{contest_id}/ranklist')
    assert participant.status_code == 200
    assert f'<td>{username}</td>' not in participant.get_data(as_text=True)


def test_admin_can_view_running_sealed_ranklist(client, app):
    with app.app_context():
        contest_id, admin_username, student_username = _create_ranked_contest(
            title='sealed_admin',
            sealed=True,
        )

    _login(client, admin_username)
    response = client.get(f'/contest/{contest_id}/ranklist')

    assert response.status_code == 200
    assert f'<td>{student_username}</td>' in response.get_data(as_text=True)


def test_sealed_ranklist_is_visible_after_contest_ends(client, app):
    with app.app_context():
        contest_id, _, username = _create_ranked_contest(
            title='sealed_ended',
            sealed=True,
            ended=True,
        )

    response = client.get(f'/contest/{contest_id}/ranklist')

    assert response.status_code == 200
    assert f'<td>{username}</td>' in response.get_data(as_text=True)
