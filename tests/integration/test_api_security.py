from app import db
from app.models.submission import Submission
from tests.utils import create_problem
from tests.utils import create_user


def _login(client, username):
    return client.post('/login', data={'username': username, 'password': 'password123'})


def test_private_problem_detail_is_hidden_from_anonymous_api(client, app):
    with app.app_context():
        problem = create_problem('Private API Problem')
        problem.is_public = False
        db.session.commit()
        problem_id = problem.id

    response = client.get(f'/api/problems/{problem_id}')

    assert response.status_code == 404


def test_private_problem_detail_is_hidden_from_anonymous_web(client, app):
    with app.app_context():
        problem = create_problem('Private Web Problem')
        problem.is_public = False
        db.session.commit()
        problem_id = problem.id

    response = client.get(f'/problem/{problem_id}')

    assert response.status_code == 404


def test_problem_api_caps_page_size(client, app):
    with app.app_context():
        create_problem('Pagination Problem')

    response = client.get('/api/problems?page=-3&per_page=10000')

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['page'] == 1
    assert data['per_page'] == 100


def test_private_problem_cannot_be_submitted_by_regular_user(client, app):
    with app.app_context():
        user = create_user('private_submitter', 'private-submitter@example.com')
        username = user.username
        problem = create_problem('Private Submit Problem')
        problem.is_public = False
        db.session.commit()
        problem_id = problem.id

    _login(client, username)
    response = client.post(
        f'/api/submit/{problem_id}',
        json={'language': 'python', 'code': 'print(1)'},
    )

    assert response.status_code == 404


def test_submission_detail_remains_private_to_owner(client, app):
    with app.app_context():
        owner = create_user('submission_owner', 'submission-owner@example.com')
        other = create_user('submission_other', 'submission-other@example.com')
        other_username = other.username
        problem = create_problem('Private Submission Detail')
        submission = Submission(
            user_id=owner.id,
            problem_id=problem.id,
            language='python',
            code='print(1)',
            status='AC',
        )
        db.session.add(submission)
        db.session.commit()
        submission_id = submission.id

    _login(client, other_username)
    response = client.get(f'/api/submission/{submission_id}')

    assert response.status_code == 403


def test_api_internal_errors_do_not_expose_exception_text(client, monkeypatch):
    def fail(_args):
        raise RuntimeError('database path and secret should stay private')

    monkeypatch.setattr('app.api.endpoints.parse_pagination', fail)
    response = client.get('/api/problems')

    assert response.status_code == 500
    assert response.get_json()['message'] == 'Internal server error'
    assert b'database path' not in response.data


def test_submission_flood_is_rate_limited_per_user(client, app):
    with app.app_context():
        user = create_user('submission_rate_user', 'submission-rate@example.com')
        problem = create_problem('Submission Rate Problem')
        username = user.username
        problem_id = problem.id

    original_limits = {
        key: app.config[key]
        for key in (
            'SUBMISSION_RATE_MAX',
            'SUBMISSION_RATE_WINDOW_SECONDS',
            'SUBMISSION_RATE_MAX_ENTRIES',
        )
    }
    try:
        app.config.update(
            SUBMISSION_RATE_MAX=1,
            SUBMISSION_RATE_WINDOW_SECONDS=60,
            SUBMISSION_RATE_MAX_ENTRIES=10,
        )
        app.extensions.pop('submission_rate_limiter', None)
        _login(client, username)

        first = client.post(
            f'/api/submit/{problem_id}',
            json={'language': 'python', 'code': 'print(1)'},
        )
        second = client.post(
            f'/api/submit/{problem_id}',
            json={'language': 'python', 'code': 'print(2)'},
        )

        assert first.status_code == 200
        assert second.status_code == 429
        assert second.headers['Retry-After'] == '60'
    finally:
        app.config.update(original_limits)
        app.extensions.pop('submission_rate_limiter', None)


def test_api_submit_rejects_non_object_json(client, app):
    with app.app_context():
        user = create_user('json_shape_user', 'json-shape@example.com')
        problem = create_problem('JSON Shape Problem')
        username = user.username
        problem_id = problem.id

    _login(client, username)

    response = client.post(f'/api/submit/{problem_id}', json=['python', 'print(1)'])

    assert response.status_code == 400
    assert response.get_json() == {'code': 400, 'message': 'JSON body must be an object'}


def test_api_submit_rejects_non_string_fields(client, app):
    with app.app_context():
        user = create_user('json_type_user', 'json-type@example.com')
        problem = create_problem('JSON Type Problem')
        username = user.username
        problem_id = problem.id

    _login(client, username)

    bad_language = client.post(
        f'/api/submit/{problem_id}',
        json={'language': ['python'], 'code': 'print(1)'},
    )
    bad_code = client.post(
        f'/api/submit/{problem_id}',
        json={'language': 'python', 'code': 123},
    )

    assert bad_language.status_code == 400
    assert bad_language.get_json() == {
        'code': 400,
        'message': 'Language and code must be strings',
    }
    assert bad_code.status_code == 400
    assert bad_code.get_json() == {
        'code': 400,
        'message': 'Language and code must be strings',
    }
