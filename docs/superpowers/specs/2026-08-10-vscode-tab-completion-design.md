# VSCode-Style Tab Completion Design

## Goal

Make the CodeMirror workspace follow the editor behavior users expect from VSCode while
preserving EasyOJ's simple OJ workflow.

## Root Cause

The enhanced editor receives keyboard events in CodeMirror, but the existing Tab handler is
attached to the hidden textarea. CodeMirror therefore runs its default indentation binding
before any EasyOJ completion behavior. Its default indentation unit is also two spaces, while
the fallback textarea and UI promise four spaces. Existing snippets use `${cursor}`, which
CodeMirror treats as named placeholder text rather than an empty cursor stop.

## Design

Configure the CodeMirror keymap so `Tab` first calls `acceptCompletion`; a false return falls
through to four-space indentation. `Shift-Tab` maps to outdent. Active snippets keep CodeMirror's
native snippet keymap, allowing Tab/Shift-Tab to move through fields. Set `indentUnit` to four
spaces for all supported languages. Replace snippet cursor markers with `${}` or numbered
`${0}` stops and add tests for the resulting contract. Keep `Ctrl+Space`, Enter, arrows, Escape,
run, and submit behavior unchanged.

## Acceptance Criteria

- With a completion list open, Tab inserts the selected option and closes the list.
- Without a completion list, Tab indents with four spaces and Shift+Tab outdents.
- Snippet insertion selects a real editable placeholder; Tab advances through fields.
- C++, Java, Python, fallback textarea, drafts, and form submission continue to work.
