# CodeMirror 6 Coding Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a project-local CodeMirror 6 editor with bounded local completions and preserve all existing EasyOJ coding flows.

**Architecture:** Build a single browser bundle from `frontend/` into `app/static/vendor/codemirror/`. The bundle mounts beside the existing textarea and exposes a narrow adapter; `code_workspace.js` uses that adapter and falls back to its current textarea path when unavailable.

**Tech Stack:** CodeMirror 6, project-local Node/esbuild, Python/pytest contract tests, browser smoke checks.

## Global Constraints

- No CDN, runtime network request, language server, or third-party source upload.
- Keep the textarea synchronized for Flask form posts, API calls, drafts, and no-JavaScript operation.
- Keep C++, Java, and Python extensible through a language registry.
- Preserve existing sandbox, CSRF, admission, and judge limits.

---

### Task 1: Define the frontend package and completion contracts

**Files:** Create `frontend/package.json`, `frontend/src/completions.mjs`, `frontend/test/completions.test.mjs`; modify `pyproject.toml` only if needed for test discovery.

- [x] Write tests asserting every supported language has non-empty keyword/snippet entries, completion labels are unique, and an input prefix returns only matching entries.
- [x] Run `node --test frontend/test/completions.test.mjs`; verify it fails because the module is absent.
- [x] Add the minimal typed completion registry and prefix filter; run the Node tests again.

### Task 2: Build the CodeMirror bundle

**Files:** Create `frontend/src/editor.mjs`, `frontend/build.mjs`; generate `app/static/vendor/codemirror/easyoj-editor.js` and `app/static/vendor/codemirror/easyoj-editor.css`.

- [x] Write the mount contract test/source assertions before implementation.
- [x] Add CodeMirror extensions for history, keymaps, brackets, folding, search, language compartments, and local completion.
- [x] Expose `window.EasyOJEditor.mount(textarea, options)` with `getValue`, `setValue`, `focus`, `replaceSelection`, `onChange`, `setLanguage`, and `destroy`.
- [x] Bundle with project-local esbuild and run the Node contract tests plus `node --check` on the generated bundle.

### Task 3: Integrate without changing judge flows

**Files:** Modify `app/templates/problems/_workspace.html`, `app/templates/problems/detail.html`, `app/templates/problems/submit.html`, `app/templates/contests/problem_detail.html`, `app/static/js/code_workspace.js`, `app/static/css/site.css`; add `tests/e2e/test_coding_editor_contract.py`.

- [x] Write failing assertions for local vendor script/CSS inclusion, textarea synchronization, and a fallback when the bundle is absent.
- [x] Mount the adapter, route all reads/writes through it, and keep legacy line-number behavior only for fallback.
- [x] Run focused Python tests, then manually verify Ctrl+Space, Tab/Enter selection, language switching, drafts, practice run, and submit.

### Task 4: Final verification and deployment notes

**Files:** Modify `README.md`, `docs/WINDOWS_DEPLOYMENT.md`, `AGENTS.md`.

- [x] Document the project-local frontend build and the fact that production serves generated static assets only.
- [x] Run full pytest, Ruff, `scripts/verify_windows.py --safe`, bounded load smoke, and the real browser flow.
