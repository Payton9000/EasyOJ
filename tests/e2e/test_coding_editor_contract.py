from pathlib import Path

from tests.utils import create_problem


def test_problem_workspace_loads_project_local_codemirror_assets(client, app):
    with app.app_context():
        problem_id = create_problem('CodeMirror Contract Problem').id

    response = client.get(f'/problem/{problem_id}')

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '/static/vendor/codemirror/easyoj-editor.js' in body
    assert '/static/vendor/codemirror/easyoj-editor.css' in body
    assert 'Ctrl+Space' in body


def test_project_local_editor_bundle_is_self_contained():
    root = Path(__file__).resolve().parents[2]
    bundle = root / 'app' / 'static' / 'vendor' / 'codemirror' / 'easyoj-editor.js'
    stylesheet = root / 'app' / 'static' / 'vendor' / 'codemirror' / 'easyoj-editor.css'

    assert bundle.is_file()
    assert stylesheet.is_file()
    assert bundle.stat().st_size > 10_000
    assert stylesheet.stat().st_size > 100


def test_enhanced_editor_preserves_textarea_accessibility_metadata():
    root = Path(__file__).resolve().parents[2]
    source = (root / 'frontend' / 'src' / 'editor.mjs').read_text(encoding='utf-8')

    assert 'EditorView.contentAttributes.of' in source
    assert "textarea.getAttribute('aria-label')" in source
    assert "textarea.getAttribute('aria-describedby')" in source


def test_workspace_contract_covers_draft_isolation_debouncing_and_keyboard_tabs():
    root = Path(__file__).resolve().parents[2]
    script = (root / 'app' / 'static' / 'js' / 'code_workspace.js').read_text(encoding='utf-8')
    template = (root / 'app' / 'templates' / 'problems' / '_workspace.html').read_text(
        encoding='utf-8'
    )

    assert 'sessionStorage' in script
    assert 'draftScope' in script
    assert 'setTimeout' in script
    assert 'clearTimeout' in script
    assert 'submission-pending' in script
    assert 'submission-complete' in script
    assert "event.key === 'Home'" in script
    assert "event.key === 'End'" in script
    assert 'aria-activedescendant' in script
    assert 'data-draft-scope' in template
    assert 'tabindex="0"' in template
    assert 'aria-labelledby="run-output-tab"' in template
    assert 'aria-labelledby="run-summary-tab"' in template


def test_submission_templates_localize_status_and_keep_machine_values():
    root = Path(__file__).resolve().parents[2]
    detail = (root / 'app' / 'templates' / 'submissions' / 'detail.html').read_text(
        encoding='utf-8'
    )
    contest_list = (root / 'app' / 'templates' / 'contests' / 'submissions.html').read_text(
        encoding='utf-8'
    )

    assert "t('submission.status.' ~ submission.status)" in detail
    assert "t('submission.status.' ~ c.status)" in detail
    assert "t('submission.status.' ~ s.status)" in contest_list
    assert 'data-status="{{ submission.status }}"' in detail


def test_editor_help_describes_completion_and_indentation_keys():
    root = Path(__file__).resolve().parents[2]
    catalogs = (root / 'app' / 'i18n' / 'catalogs.py').read_text(encoding='utf-8')

    assert 'Tab accepts a completion or inserts four spaces. Shift+Tab outdents.' in catalogs
    assert 'Tab 接受补全或插入四个空格；Shift+Tab 减少缩进。' in catalogs
