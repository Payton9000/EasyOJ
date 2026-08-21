from app import create_app
from app import db
from app.models.contest import Contest
from app.models.contest_participant import ContestParticipant
from app.models.contest_problem import ContestProblem
from app.models.submission import Submission
from app.models.user import User


def test_automated_contest_flow_is_bounded_and_judges_five_concurrent_users(tmp_path):
    from scripts.demo_automated_contest import run_demo

    base_dir = tmp_path / 'base'
    db_path = tmp_path / 'database.sqlite'
    result = run_demo(
        db_path=db_path,
        base_dir=base_dir,
        timeout_seconds=20,
    )

    assert result['contest_id'] > 0
    assert result['participant_count'] == 5
    assert len(result['submission_ids']) == 5
    assert result['statuses'] == ['AC'] * 5
    assert result['elapsed_seconds'] <= 20

    inspect_app = create_app(
        'testing',
        start_judge_engine=False,
        config_overrides={
            'BASE_DIR': str(base_dir),
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        },
    )
    with inspect_app.app_context():
        contest = db.session.get(Contest, result['contest_id'])
        assert contest is not None
        assert contest.creator.username == 'demo_admin'
        assert User.query.filter(User.username.like('demo_user_%')).count() == 5
        assert ContestProblem.query.filter_by(contest_id=contest.id, alias='A').count() == 1
        assert ContestParticipant.query.filter_by(contest_id=contest.id).count() == 5
        submissions = (
            Submission.query.filter_by(contest_id=contest.id).order_by(Submission.user_id).all()
        )
        assert [submission.status for submission in submissions] == ['AC'] * 5


def test_run_demo_releases_sqlite_handles_before_temp_cleanup(tmp_path):
    from scripts.demo_automated_contest import run_demo

    base_dir = tmp_path / 'base'
    db_path = tmp_path / 'database.sqlite'
    run_demo(db_path=db_path, base_dir=base_dir, timeout_seconds=20)

    db_path.unlink()
    assert not db_path.exists()
