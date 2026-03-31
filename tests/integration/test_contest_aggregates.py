from contextlib import contextmanager
from datetime import datetime, timedelta

from flask import template_rendered

from app import db
from app.models.contest import Contest
from app.models.contest_participant import ContestParticipant
from app.models.contest_problem import ContestProblem
from app.models.submission import Submission
from tests.utils import create_problem, create_user


def _login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)


@contextmanager
def captured_templates(app):
    recorded = []

    def _record(sender, template, context, **extra):
        recorded.append((template, context))

    template_rendered.connect(_record, app)
    try:
        yield recorded
    finally:
        template_rendered.disconnect(_record, app)


def test_ranklist_is_computed_from_aggregates(client, app):
    with app.app_context():
        user1 = create_user('rank_u1', 'rank_u1@example.com')
        user2 = create_user('rank_u2', 'rank_u2@example.com')
        user3 = create_user('rank_u3', 'rank_u3@example.com')

        problem1 = create_problem('Rank Problem A')
        problem2 = create_problem('Rank Problem B')

        start_time = datetime.utcnow() - timedelta(hours=1)
        contest = Contest(
            title='Aggregate Rank Contest',
            description='ranklist test',
            start_time=start_time,
            end_time=start_time + timedelta(hours=3),
            is_public=True,
            created_by=user1.id,
        )
        db.session.add(contest)
        db.session.commit()

        cp1 = ContestProblem(contest_id=contest.id, problem_id=problem1.id, display_order=1, alias='A')
        cp2 = ContestProblem(contest_id=contest.id, problem_id=problem2.id, display_order=2, alias='B')
        db.session.add_all([cp1, cp2])
        db.session.add_all([
            ContestParticipant(contest_id=contest.id, user_id=user1.id),
            ContestParticipant(contest_id=contest.id, user_id=user2.id),
            ContestParticipant(contest_id=contest.id, user_id=user3.id),
        ])

        submissions = [
            Submission(
                user_id=user1.id,
                problem_id=problem1.id,
                contest_id=contest.id,
                language='python',
                code='print(1)',
                status='WA',
                submitted_at=start_time + timedelta(minutes=5),
            ),
            Submission(
                user_id=user1.id,
                problem_id=problem1.id,
                contest_id=contest.id,
                language='python',
                code='print(2)',
                status='AC',
                submitted_at=start_time + timedelta(minutes=10),
            ),
            Submission(
                user_id=user1.id,
                problem_id=problem2.id,
                contest_id=contest.id,
                language='python',
                code='print(3)',
                status='AC',
                submitted_at=start_time + timedelta(minutes=15),
            ),
            Submission(
                user_id=user2.id,
                problem_id=problem1.id,
                contest_id=contest.id,
                language='python',
                code='print(4)',
                status='AC',
                submitted_at=start_time + timedelta(minutes=7),
            ),
            Submission(
                user_id=user2.id,
                problem_id=problem2.id,
                contest_id=contest.id,
                language='python',
                code='print(5)',
                status='WA',
                submitted_at=start_time + timedelta(minutes=8),
            ),
        ]
        db.session.add_all(submissions)
        db.session.commit()

        ranklist = contest.get_ranklist()
        cp1_id = cp1.id
        cp2_id = cp2.id

    assert [item['user'].username for item in ranklist] == ['rank_u1', 'rank_u2', 'rank_u3']

    by_username = {item['user'].username: item for item in ranklist}

    assert by_username['rank_u1']['solved'] == 2
    assert by_username['rank_u1']['penalty'] == 45
    assert by_username['rank_u1']['problems'][cp1_id]['status'] == 'AC'
    assert by_username['rank_u1']['problems'][cp1_id]['attempts'] == 2
    assert by_username['rank_u1']['problems'][cp1_id]['ac_time'] == 10

    assert by_username['rank_u2']['solved'] == 1
    assert by_username['rank_u2']['penalty'] == 7
    assert by_username['rank_u2']['problems'][cp2_id]['status'] == 'WA'

    assert by_username['rank_u3']['solved'] == 0
    assert by_username['rank_u3']['penalty'] == 0


def test_contest_detail_problem_stats_are_grouped_once(client, app):
    with app.app_context():
        user1 = create_user('detail_u1', 'detail_u1@example.com')
        user2 = create_user('detail_u2', 'detail_u2@example.com')

        problem1 = create_problem('Detail Problem A')
        problem2 = create_problem('Detail Problem B')

        now = datetime.utcnow()
        contest = Contest(
            title='Aggregate Detail Contest',
            description='detail stats test',
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            is_public=True,
            created_by=user1.id,
        )
        db.session.add(contest)
        db.session.commit()

        cp1 = ContestProblem(contest_id=contest.id, problem_id=problem1.id, display_order=1, alias='A')
        cp2 = ContestProblem(contest_id=contest.id, problem_id=problem2.id, display_order=2, alias='B')
        db.session.add_all([cp1, cp2])
        db.session.add_all([
            ContestParticipant(contest_id=contest.id, user_id=user1.id),
            ContestParticipant(contest_id=contest.id, user_id=user2.id),
        ])
        db.session.add_all([
            Submission(user_id=user1.id, problem_id=problem1.id, contest_id=contest.id,
                       language='python', code='print(1)', status='WA'),
            Submission(user_id=user1.id, problem_id=problem1.id, contest_id=contest.id,
                       language='python', code='print(2)', status='AC'),
            Submission(user_id=user2.id, problem_id=problem1.id, contest_id=contest.id,
                       language='python', code='print(3)', status='WA'),
            Submission(user_id=user1.id, problem_id=problem2.id, contest_id=contest.id,
                       language='python', code='print(4)', status='AC'),
            Submission(user_id=user2.id, problem_id=problem2.id, contest_id=contest.id,
                       language='python', code='print(5)', status='AC'),
            Submission(user_id=user2.id, problem_id=problem2.id, contest_id=contest.id,
                       language='python', code='print(6)', status='WA'),
        ])
        db.session.commit()
        contest_id = contest.id

    _login(client, 'detail_u1', 'password123')

    with captured_templates(app) as templates:
        response = client.get(f'/contest/{contest_id}')

    assert response.status_code == 200
    assert templates

    _, context = templates[-1]
    stats_by_alias = {
        item['contest_problem'].alias: (item['submitted_count'], item['accepted_count'])
        for item in context['problem_stats']
    }

    assert stats_by_alias['A'] == (2, 1)
    assert stats_by_alias['B'] == (2, 2)
