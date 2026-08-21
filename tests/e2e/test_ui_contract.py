import re
from pathlib import Path


def test_base_uses_static_conventional_oj_styles(client):
    response = client.get('/login')
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '/static/css/site.css' in body
    assert 'themeToggle' not in body
    assert 'data-theme' not in body
    assert 'linear-gradient' not in body


def test_auth_form_contains_csrf_token(client):
    response = client.get('/login')
    body = response.get_data(as_text=True)

    assert 'name="csrf_token"' in body


def test_problem_list_exposes_clear_filter_and_empty_state(client):
    response = client.get('/problems?q=does-not-exist')
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'name="q"' in body
    assert 'empty-state' in body


def test_every_post_form_has_csrf_token():
    template_root = Path(__file__).parents[2] / 'app' / 'templates'
    missing = []
    pattern = re.compile(r'<form\b[^>]*method\s*=\s*["\']POST["\'][^>]*>.*?</form>', re.I | re.S)
    for path in template_root.rglob('*.html'):
        text = path.read_text(encoding='utf-8')
        for match in pattern.finditer(text):
            if not re.search(r'name\s*=\s*["\']csrf_token["\']', match.group(0), re.I):
                missing.append(str(path))

    assert missing == []
