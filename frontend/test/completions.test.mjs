import assert from 'node:assert/strict';
import test from 'node:test';

import {
    LANGUAGE_COMPLETIONS,
    filterCompletionOptions,
    getCompletionOptions,
} from '../src/completions.mjs';

test('each supported language exposes unique completion entries', () => {
    for (const language of ['cpp', 'java', 'python']) {
        const options = getCompletionOptions(language);
        assert.ok(options.length >= 8, language);
        assert.equal(new Set(options.map((option) => option.label)).size, options.length);
        assert.ok(options.every((option) => option.type && option.apply));
    }
    assert.deepEqual(Object.keys(LANGUAGE_COMPLETIONS).sort(), ['cpp', 'java', 'python']);
});

test('completion filtering is case-sensitive and bounded to the selected language', () => {
    assert.deepEqual(
        filterCompletionOptions('python', 'pri').map((option) => option.label),
        ['print']
    );
    assert.deepEqual(
        filterCompletionOptions('cpp', 'pri').map((option) => option.label),
        ['priority_queue', 'priority_queue<int>']
    );
    assert.deepEqual(filterCompletionOptions('unknown', 'pri'), []);
});

test('empty prefixes return a predictable capped list', () => {
    const options = filterCompletionOptions('java', '');
    assert.ok(options.length <= 40);
    assert.ok(options.length > 0);
});

test('each language provides at least one cursor-aware snippet', () => {
    for (const language of ['cpp', 'java', 'python']) {
        const snippets = getCompletionOptions(language).filter(
            (option) => option.type === 'snippet'
        );
        assert.ok(snippets.length > 0, language);
        assert.ok(snippets.every((option) => option.apply.includes('${1}')), language);
        assert.ok(snippets.every((option) => option.apply.includes('${0}')), language);
        assert.ok(snippets.every((option) => !option.apply.includes('${cursor}')), language);
    }
});
