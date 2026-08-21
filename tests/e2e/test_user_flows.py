def test_login_redirects_user_to_password_change_when_required(client, app):
    from app import db
    from app.models.user import User

    with app.app_context():
        user = User(
            username='forced_change_user',
            email='forced-change@example.com',
            must_change_password=True,
        )
        user.set_password('abc12345')
        db.session.add(user)
        db.session.commit()
        username = user.username

    response = client.post('/login', data={'username': username, 'password': 'abc12345'})

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/change-password')
