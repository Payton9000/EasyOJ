import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const editorSource = readFileSync(new URL('../src/editor.mjs', import.meta.url), 'utf8');
const completionSource = readFileSync(new URL('../src/completions.mjs', import.meta.url), 'utf8');

test('Tab accepts an open completion before falling back to indentation', () => {
    assert.match(editorSource, /acceptCompletion/);
    assert.match(editorSource, /function acceptCompletionOrIndent\(view\)/);
    assert.match(editorSource, /return acceptCompletion\(view\) \|\| indentMore\(view\);/);
    assert.match(editorSource, /indentUnit\.of\('    '\)/);
    assert.match(editorSource, /\{ key: 'Tab', run: acceptCompletionOrIndent \}/);
    assert.match(editorSource, /\{ key: 'Shift-Tab', run: indentLess \}/);
});

test('completion snippets use real CodeMirror cursor stops', () => {
    assert.doesNotMatch(completionSource, /\$\{cursor\}/);
    assert.match(completionSource, /\$\{1\}/);
    assert.match(completionSource, /\$\{0\}/);
});
