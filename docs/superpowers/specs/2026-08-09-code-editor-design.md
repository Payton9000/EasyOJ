# CodeMirror 6 Coding Workspace Design

**Goal:** Replace the workspace's plain textarea interaction with a lightweight,
offline-capable editor that provides VS Code-like editing assistance while
preserving the existing form, draft, practice-run, and submission contracts.

## Scope

The browser editor will provide syntax highlighting for the currently selected
C++, Java, or Python language; completion popups (including `Ctrl+Space`),
bracket matching/closing, automatic indentation, folding, search, multi-cursor
editing, and a small local snippet/keyword catalog. It will not start a
language server or send source code to a third party. Semantic completion is
out of scope because OJ submissions are single files with no project context.

## Architecture

`frontend/` contains the project-local package manifest, source modules, build
script, and pure completion-catalog tests. The build emits one pinned,
self-contained browser bundle under `app/static/vendor/codemirror/`; deployment
serves that file locally and does not require Node.js. The existing
`data-code-editor` textarea remains in the DOM as the form's synchronized source
of truth and as a no-JavaScript fallback. A small adapter exposes
`getValue`, `setValue`, `focus`, `replaceSelection`, `onChange`, and
`setLanguage` to `code_workspace.js`, so run/submit/draft behavior remains
unchanged.

## Completion Design

Completion sources are selected by language and are entirely local. Common
control-flow words and OJ snippets are shared; Python adds built-ins, C++ adds
common STL types/algorithms, and Java adds common `java.util`/`java.lang` names.
Each entry can carry a short detail label and a safe replacement string. A
language registry makes adding a future language a data/configuration change,
not a route change.

## Safety and Failure Handling

The bundle is static and same-origin. If it fails to load, the textarea and
existing keyboard behavior continue to work. Editor changes always mirror to
the textarea before fetch or form submission; changing language destroys no
draft. Completion is bounded to local arrays and never invokes the judge.

## Verification

Add contract tests for the vendor asset/template wiring and Node tests for
completion catalogs. Use `node --check`, the existing pytest/Ruff gates, and a
real browser smoke test covering language switching, `Ctrl+Space`, a snippet
insertion, draft persistence, practice run, and normal submission.
