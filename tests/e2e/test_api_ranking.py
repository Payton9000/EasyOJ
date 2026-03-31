from tests.utils import create_problem, create_user, write_testcases


def test_api_ranking_endpoint(client, app):
    with app.app_context():
        create_user('rank_user1', 'rank1@example.com')
        create_user('rank_user2', 'rank2@example.com')
        problem = create_problem('Rank Test')
        write_testcases(app.config['BASE_DIR'], problem.id, [('1 2', '3')])

    res = client.get('/api/ranking')
    assert res.status_code == 200
    data = res.get_json()['data']
    assert isinstance(data, list)
    assert len(data) >= 1
    assert 'username' in data[0]
    assert 'ac_count' in data[0]
