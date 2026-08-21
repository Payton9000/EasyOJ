from datetime import datetime
from datetime import timedelta
from pathlib import Path

from app import db
from app.models.contest import Contest
from app.models.contest_participant import ContestParticipant
from app.models.contest_problem import ContestProblem
from tests.utils import create_problem
from tests.utils import create_user


def _login(client, username, password='password123'):
    return client.post(
        '/login',
        data={'username': username, 'password': password},
        follow_redirects=True,
    )


def _workspace_body(response):
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_public_problem_has_two_pane_workspace_and_anonymous_state(client, app):
    with app.app_context():
        problem = create_problem('Workspace Contract Problem')
        problem_id = problem.id

    body = _workspace_body(client.get(f'/problem/{problem_id}'))

    assert 'class="coding-workspace"' in body
    assert 'workspace-statement' in body
    assert 'workspace-editor' in body
    for element_id in ('code-editor', 'custom-input', 'run-code', 'submit-code', 'run-result'):
        assert f'id="{element_id}"' in body
    assert 'disabled' in body
    assert 'data-workspace-key="problem:' in body
    assert f'data-run-url="/api/run/{problem_id}"' in body
    assert '/static/js/code_workspace.js' in body
    assert 'workspace.statement' in body or 'Statement' in body


def test_authenticated_submit_workspace_preserves_post_action_and_csrf(client, app):
    with app.app_context():
        user = create_user('workspace_submit_user', 'workspace-submit@example.com')
        problem = create_problem('Submit Workspace Contract Problem')
        problem_id = problem.id
        username = user.username

    _login(client, username)
    body = _workspace_body(client.get(f'/problem/{problem_id}/submit'))

    assert f'action="/problem/{problem_id}/submit"' in body
    assert 'method="POST"' in body
    assert 'name="csrf_token"' in body
    assert 'name="language"' in body
    assert 'name="code"' in body
    assert 'id="submit-code"' in body
    assert 'data-authenticated="true"' in body


def test_contest_workspace_uses_contest_submission_action(client, app):
    with app.app_context():
        user = create_user('workspace_contest_user', 'workspace-contest@example.com')
        now = datetime.utcnow()
        contest = Contest(
            title='Workspace Contract Contest',
            description='Contract',
            start_time=now - timedelta(minutes=5),
            end_time=now + timedelta(minutes=55),
            is_public=True,
            created_by=user.id,
        )
        db.session.add(contest)
        db.session.flush()
        problem = create_problem('Contest Workspace Contract Problem')
        contest_problem = ContestProblem(
            contest_id=contest.id,
            problem_id=problem.id,
            alias='A',
            display_order=1,
        )
        db.session.add_all(
            [contest_problem, ContestParticipant(contest_id=contest.id, user_id=user.id)]
        )
        db.session.commit()
        contest_id = contest.id
        username = user.username

    _login(client, username)
    body = _workspace_body(client.get(f'/contest/{contest_id}/problem/A'))

    assert f'action="/contest/{contest_id}/submit/A"' in body
    assert f'data-workspace-key="contest:{contest_id}:A"' in body
    assert 'name="csrf_token"' in body
    assert 'aria-live="polite"' in body
    assert 'data-submit-shortcut="Ctrl+Shift+Enter"' in body


def test_workspace_assets_define_responsive_editor_enhancement():
    root = Path(__file__).resolve().parents[2]
    script = (root / 'app' / 'static' / 'js' / 'code_workspace.js').read_text(encoding='utf-8')
    stylesheet = (root / 'app' / 'static' / 'css' / 'site.css').read_text(encoding='utf-8')

    assert 'localStorage' in script
    assert 'payload.data' in script
    assert 'currentLanguage' in script
    assert 'selectionStart' in script
    assert 'insertText' in script
    assert 'ctrlKey' in script and 'shiftKey' in script
    assert 'data-line-numbers' in script
    assert 'data-result-tab' in script
    assert '.coding-workspace' in stylesheet
    assert '.workspace-statement' in stylesheet
    assert '.workspace-editor' in stylesheet
    assert '@media (max-width: 900px)' in stylesheet


def test_workspace_template_exposes_run_metadata_and_accessible_states():
    root = Path(__file__).resolve().parents[2]
    template = (root / 'app' / 'templates' / 'problems' / '_workspace.html').read_text(
        encoding='utf-8'
    )

    assert "t('workspace.statement')" in template
    assert 'data-run-url="{{ run_url | default(\'\', true) }}"' in template
    assert 'aria-busy="false"' in template
    assert 'role="tablist"' in template
    assert 'data-line-numbers' in template
    assert 'data-clear-draft' in template
