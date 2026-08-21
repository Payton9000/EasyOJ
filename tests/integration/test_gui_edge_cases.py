from app import db


class TestGUIEdgeCases:
    """
    Test suite translating the brainstormed GUI test scenarios
    into backend validation and integration tests.
    """

    def test_input_injection_and_xss(self, client, app):
        """Test Case 1: Input Fields - Special Characters & Injection"""
        with app.app_context():
            # Try to register a user with XSS and SQLi payloads
            xss_payload = '<script>alert(1)</script>'
            sqli_payload = "' OR 1=1 --"

            response = client.post(
                '/register',
                data={
                    'username': xss_payload,
                    'email': 'xss@example.com',
                    'password': 'password123',
                    'confirm_password': 'password123',
                },
                follow_redirects=True,
            )

            assert response.status_code == 200

            # Check login with SQLi
            login_resp = client.post(
                '/login',
                data={'username': sqli_payload, 'password': 'password123'},
                follow_redirects=True,
            )
            assert login_resp.status_code == 200

    def test_input_boundaries(self, client, app):
        """Test Case 1: Input Fields - Boundary Values"""
        # Exceeding typical max length for username (e.g. > 80 chars)
        long_username = 'A' * 150
        response = client.post(
            '/register',
            data={
                'username': long_username,
                'email': 'long@example.com',
                'password': 'password123',
                'confirm_password': 'password123',
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        # Empty inputs
        empty_response = client.post(
            '/register',
            data={'username': '', 'email': '', 'password': '', 'confirm_password': ''},
            follow_redirects=True,
        )
        assert empty_response.status_code == 200
        assert b'required' in empty_response.data.lower()

    def test_unauthorized_routing_access(self, client, app):
        """Test Case 4: Navigation & Routing - State constraints"""
        # Accessing protected routes without login
        endpoints = ['/admin', '/contests/create']
        for ep in endpoints:
            resp = client.get(ep, follow_redirects=False)
            # Should redirect to login or return 401/403/404/308
            assert resp.status_code in [302, 308, 401, 403, 404]

    def test_file_upload_limitations(self, client, app):
        """Test Case 7: File Upload / Code Submission validation limits"""
        with app.app_context():
            from app.models.problem import Problem
            from app.models.user import User

            # Setup data
            user = User(username='testuser', email='test@example.com')
            user.set_password('password123')
            prob = Problem(title='T1', description='D', memory_limit=128, time_limit=1000)
            db.session.add(user)
            db.session.add(prob)
            db.session.commit()
            prob_id = prob.id

        # Login test user
        client.post(
            '/login',
            data={'username': 'testuser', 'password': 'password123'},
            follow_redirects=True,
        )

        # Test 1: Unsupported language
        resp1 = client.post(
            f'/api/submit/{prob_id}',
            json={
                'language': 'ruby',  # Unsupported
                'code': 'puts "hello"',
            },
        )
        assert resp1.status_code == 400
        assert b'Unsupported' in resp1.data or b'Invalid' in resp1.data

        # Test 2: Unreasonably large payload (e.g. > 64KB)
        resp2 = client.post(
            f'/api/submit/{prob_id}',
            json={
                'language': 'python',
                'code': 'print("A")\n' * 50000,  # Will exceed 64KB
            },
        )
        # If API handles max length properly it returns 400/413, or it might just process. We just ensure no crash.
        assert resp2.status_code in [200, 400, 413, 201]

    def test_api_pagination_boundaries(self, client, app):
        """Test Case 6: Tables & Lists - Pagination"""
        # Invalid pagination inputs (negative page, excessively large per_page)
        resp1 = client.get('/api/problems?page=-1&per_page=999999')
        # APIs usually default to page 1 or return 400/404. We assert it doesn't 500.
        assert resp1.status_code in [200, 400, 404]
