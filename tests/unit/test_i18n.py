from app.i18n import translate
from app.i18n.catalogs import CATALOGS


def test_translate_returns_english_and_chinese_catalog_values():
    assert translate('nav.problems', locale='en') == 'Problems'
    assert translate('nav.problems', locale='zh-CN') == '题库'


def test_translate_interpolates_values_and_falls_back_to_key():
    assert translate('submission.number', locale='zh-CN', number=17) == '提交 #17'
    assert translate('missing.key', locale='en') == 'missing.key'


def test_translate_does_not_crash_when_a_placeholder_value_is_missing():
    assert translate('submission.number', locale='en', unexpected=17) == 'Submission #{number}'


def test_submission_statuses_are_localized_in_both_catalogs_without_changing_machine_values():
    statuses = (
        'Pending',
        'Queued',
        'Judging',
        'AC',
        'WA',
        'CE',
        'RE',
        'TLE',
        'MLE',
        'OLE',
        'Failed',
        'SystemError',
        'OK',
        'Busy',
        'Invalid',
    )

    assert set(CATALOGS['en']) == set(CATALOGS['zh-CN'])
    for status in statuses:
        key = f'submission.status.{status}'
        assert translate(key, locale='en') != key
        assert translate(key, locale='zh-CN') != key
    assert translate('submission.status.AC', locale='en') == 'Accepted'
    assert translate('submission.status.AC', locale='zh-CN') == '通过'


def test_locale_uses_browser_preference_by_default(client):
    response = client.get('/problems', headers={'Accept-Language': 'zh-CN,zh;q=0.9'})

    assert response.status_code == 200
    assert '<html lang="zh-CN">' in response.get_data(as_text=True)


def test_locale_switch_persists_in_session(client):
    response = client.post('/language/zh-CN', follow_redirects=False)

    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session['locale'] == 'zh-CN'


def test_locale_switch_rejects_unknown_locale(client):
    response = client.post('/language/fr', follow_redirects=False)

    assert response.status_code == 400


def test_locale_switch_returns_to_same_host_page(client):
    response = client.post(
        '/language/zh-CN',
        headers={'Referer': 'http://localhost/problem/14?from=workspace'},
        follow_redirects=False,
    )

    assert response.headers['Location'] == '/problem/14?from=workspace'


def test_locale_switch_rejects_external_referrer(client):
    response = client.post(
        '/language/zh-CN',
        headers={'Referer': 'https://example.com/steal-session'},
        follow_redirects=False,
    )

    assert response.headers['Location'] == '/problems'
