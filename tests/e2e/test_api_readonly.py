from tests.utils import create_problem


def test_api_problem_list_and_detail(client, app):
    with app.app_context():
        problem_id = create_problem('Readonly Test').id

    res = client.get('/api/problems')
    assert res.status_code == 200
    data = res.get_json()['data']
    assert data['total'] >= 1

    res = client.get(f'/api/problems/{problem_id}')
    assert res.status_code == 200
    detail = res.get_json()['data']
    assert detail['id'] == problem_id
    assert detail['title'] == 'Readonly Test'
