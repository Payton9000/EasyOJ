import {
    acceptCompletion,
    autocompletion,
    closeBrackets,
    closeBracketsKeymap,
    completionKeymap,
    snippetCompletion,
    startCompletion,
} from '@codemirror/autocomplete';
import {
    defaultKeymap,
    history,
    historyKeymap,
    indentLess,
    indentMore,
} from '@codemirror/commands';
import { cpp } from '@codemirror/lang-cpp';
import { java } from '@codemirror/lang-java';
import { python } from '@codemirror/lang-python';
import {
    bracketMatching,
    defaultHighlightStyle,
    foldGutter,
    foldKeymap,
    indentOnInput,
    indentUnit,
    syntaxHighlighting,
} from '@codemirror/language';
import { highlightSelectionMatches, searchKeymap } from '@codemirror/search';
import { Compartment, EditorState } from '@codemirror/state';
import {
    crosshairCursor,
    drawSelection,
    dropCursor,
    EditorView,
    highlightActiveLine,
    highlightActiveLineGutter,
    highlightSpecialChars,
    keymap,
    lineNumbers,
    rectangularSelection,
} from '@codemirror/view';

import { getCompletionOptions } from './completions.mjs';

const languageSupport = Object.freeze({
    cpp: cpp(),
    java: java(),
    python: python(),
});

function normalizeLanguage(language) {
    return Object.hasOwn(languageSupport, language) ? language : 'cpp';
}

function editorCompletions(language) {
    return getCompletionOptions(language).map((option) => {
        const metadata = {
            label: option.label,
            type: option.type,
            detail: option.detail,
        };
        if (option.type === 'snippet') {
            return snippetCompletion(option.apply, metadata);
        }
        return { ...metadata, apply: option.apply };
    });
}

function createCompletionSource(getLanguage) {
    return (context) => {
        const word = context.matchBefore(/[A-Za-z_#][\w.]*/);
        if (!context.explicit && (!word || word.from === word.to)) {
            return null;
        }
        return {
            from: word ? word.from : context.pos,
            options: editorCompletions(getLanguage()),
            validFor: /^[A-Za-z_#][\w.]*$/,
        };
    };
}

function shortcut(run) {
    return () => {
        if (typeof run !== 'function') {
            return false;
        }
        run();
        return true;
    };
}

function acceptCompletionOrIndent(view) {
    return acceptCompletion(view) || indentMore(view);
}

export function mount(textarea, options = {}) {
    if (!textarea || !textarea.parentElement || textarea.dataset.enhancedEditor === 'true') {
        return null;
    }

    const host = document.createElement('div');
    host.className = 'workspace-codemirror-host';
    host.dataset.codingEditor = 'codemirror';
    textarea.parentElement.insertBefore(host, textarea);

    const languageCompartment = new Compartment();
    const listeners = new Set();
    let currentLanguage = normalizeLanguage(options.language);
    const source = createCompletionSource(() => currentLanguage);
    const originalRequired = textarea.required;
    const contentAttributes = {
        'aria-label': textarea.getAttribute('aria-label') || 'Source code',
        'aria-multiline': 'true',
        spellcheck: 'false',
    };
    const describedBy = textarea.getAttribute('aria-describedby');
    if (describedBy) {
        contentAttributes['aria-describedby'] = describedBy;
    }
    if (originalRequired) {
        contentAttributes['aria-required'] = 'true';
    }

    const state = EditorState.create({
        doc: textarea.value,
        extensions: [
            lineNumbers(),
            highlightActiveLineGutter(),
            highlightSpecialChars(),
            history(),
            foldGutter(),
            drawSelection(),
            dropCursor(),
            EditorState.allowMultipleSelections.of(true),
            indentOnInput(),
            indentUnit.of('    '),
            syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
            bracketMatching(),
            closeBrackets(),
            autocompletion({ activateOnTyping: true, override: [source], maxRenderedOptions: 40 }),
            rectangularSelection(),
            crosshairCursor(),
            highlightActiveLine(),
            highlightSelectionMatches(),
            EditorView.contentAttributes.of(contentAttributes),
            languageCompartment.of(languageSupport[currentLanguage]),
            keymap.of([
                { key: 'Mod-Enter', run: shortcut(options.onRun) },
                { key: 'Mod-Shift-Enter', run: shortcut(options.onSubmit) },
                { key: 'Mod-Space', run: startCompletion },
                { key: 'Tab', run: acceptCompletionOrIndent },
                { key: 'Shift-Tab', run: indentLess },
                ...closeBracketsKeymap,
                ...completionKeymap,
                ...searchKeymap,
                ...historyKeymap,
                ...foldKeymap,
                ...defaultKeymap,
            ]),
            EditorView.updateListener.of((update) => {
                if (!update.docChanged) {
                    return;
                }
                textarea.value = update.state.doc.toString();
                textarea.dispatchEvent(new Event('input', { bubbles: true }));
                listeners.forEach((listener) => listener(textarea.value));
            }),
        ],
    });

    let view;
    try {
        view = new EditorView({ state, parent: host });
    } catch (error) {
        host.remove();
        return null;
    }

    textarea.required = false;
    textarea.hidden = true;
    textarea.dataset.enhancedEditor = 'true';
    textarea.parentElement.classList.add('is-enhanced');

    return Object.freeze({
        isEnhanced: true,
        getValue() {
            return view.state.doc.toString();
        },
        setValue(value) {
            const next = typeof value === 'string' ? value : '';
            if (next === view.state.doc.toString()) {
                return;
            }
            view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: next } });
        },
        focus() {
            view.focus();
        },
        replaceSelection(text) {
            view.dispatch(view.state.replaceSelection(String(text)));
            view.focus();
        },
        onChange(listener) {
            if (typeof listener !== 'function') {
                return () => {};
            }
            listeners.add(listener);
            return () => listeners.delete(listener);
        },
        setLanguage(language) {
            const next = normalizeLanguage(language);
            if (next === currentLanguage) {
                return;
            }
            currentLanguage = next;
            view.dispatch({ effects: languageCompartment.reconfigure(languageSupport[next]) });
        },
        destroy() {
            view.destroy();
            listeners.clear();
            host.remove();
            textarea.hidden = false;
            textarea.required = originalRequired;
            delete textarea.dataset.enhancedEditor;
            textarea.parentElement.classList.remove('is-enhanced');
        },
    });
}

if (typeof window !== 'undefined') {
    window.EasyOJEditor = Object.freeze({ mount, version: '1.0.0' });
}
