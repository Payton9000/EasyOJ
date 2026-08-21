import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync(new URL('../../app/static/js/code_workspace.js', import.meta.url), 'utf8');

test('workspace isolates drafts and delays persistence', () => {
    assert.match(source, /sessionStorage/);
    assert.match(source, /draftScope/);
    assert.match(source, /setTimeout/);
    assert.match(source, /clearTimeout/);
});

test('workspace preserves drafts until a confirmed submission completion', () => {
    assert.match(source, /submission-pending/);
    assert.match(source, /submission-complete/);
    assert.match(source, /removeItem\(draftKey\(\)\)/);
});

test('result tabs support the complete keyboard navigation contract', () => {
    assert.match(source, /ArrowLeft/);
    assert.match(source, /ArrowRight/);
    assert.match(source, /event\.key === 'Home'/);
    assert.match(source, /event\.key === 'End'/);
    assert.match(source, /aria-activedescendant/);
});
