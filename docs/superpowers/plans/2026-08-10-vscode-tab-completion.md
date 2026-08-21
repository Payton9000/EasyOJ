# VSCode-Style Tab Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Align EasyOJ's online editor keyboard behavior with VSCode's Tab completion and indentation conventions.

**Architecture:** Keep CodeMirror responsible for enhanced-editor keyboard handling and keep the textarea listener as the safe fallback. Add a small, explicit keymap layer around CodeMirror's existing completion and snippet commands, and configure one shared four-space indentation facet.

**Tech Stack:** CodeMirror 6, `@codemirror/autocomplete`, `@codemirror/commands`, Node's built-in test runner, pnpm/esbuild.

## Global Constraints

- Preserve project-local CodeMirror assets and the existing C++/Java/Python language switch.
- Keep `Ctrl+Space`, Enter, arrows, Escape, run, submit, draft persistence, and accessibility metadata working.
- Use four literal spaces as the editor indentation unit; do not introduce a global dependency.
- Add tests before production changes and keep the fallback textarea path intact.

### Task 1: Lock the editor contract with failing tests

**Files:**
- Create: `frontend/test/editor_keymap.test.mjs`
- Modify: `frontend/test/completions.test.mjs`

- [ ] Assert the source imports `acceptCompletion`, configures `indentUnit.of('    ')`, binds Tab before indentation, and binds Shift-Tab to outdent.
- [ ] Assert every snippet uses an empty or numbered cursor stop and no `${cursor}` literal.
- [ ] Run `pnpm --dir frontend test`; expected result is a failure identifying the missing Tab/indent/snippet behavior.

### Task 2: Implement completion-aware keyboard behavior

**Files:**
- Modify: `frontend/src/editor.mjs`
- Modify: `frontend/src/completions.mjs`

- [ ] Import `acceptCompletion`, `indentLess`, and `indentUnit`.
- [ ] Add a Tab binding whose command returns false when no completion is active, followed by the existing indentation binding; add explicit Shift-Tab outdent support.
- [ ] Add `indentUnit.of('    ')` and replace `${cursor}` with `${}`/`${0}` stops.
- [ ] Run the focused frontend tests and confirm they pass.

### Task 3: Build and verify the integrated workspace

**Files:**
- Modify: `app/i18n/catalogs.py`
- Modify: `app/templates/problems/_workspace.html`
- Modify: `tests/e2e/test_coding_editor_contract.py`

- [ ] Update the bilingual editor hint to describe Tab completion, Tab indentation, and Shift-Tab outdent.
- [ ] Add a template contract assertion for the new hint.
- [ ] Build project-local editor assets, run frontend tests, backend editor contracts, Ruff, and the bounded Windows smoke check.
