# Bilingual Coding Workspace Design

## Goal

Provide complete Chinese/English fixed UI text and a restrained LeetCode-style coding
workspace while keeping problem statements in their existing single database language.

## Internationalization

Use a dependency-free server-side catalog (`en` and `zh-CN`) exposed to Python and
Jinja. Locale selection follows an explicit session choice, then browser preference,
then English. A CSRF-protected language switch updates the session. Navigation, public
pages, authentication, contests, submissions, administration, validation messages, and
error pages use stable translation keys. User-created database text is rendered verbatim.

## Coding Workspace

Problem and contest problem pages use a responsive two-pane layout: statement on the
left, editor on the right, with language selector, source editor, custom input, output
console, Run, and Submit controls. Narrow screens stack the panes. The editor is a local
textarea enhanced with line numbers, Tab indentation, keyboard shortcuts, and per-problem
draft persistence; no CDN, Node runtime, or global dependency is required.

Custom runs use a CSRF-protected JSON endpoint and a bounded service. Input and source
size are validated, at most one custom run executes concurrently by default, and code
uses the same fail-closed compiler, AppContainer, Job Object, output, time, memory, process,
and workspace controls as judged submissions. Custom runs do not create ranked submissions.

## UX and Errors

Run and Submit are distinct and labelled. Pending controls disable duplicate clicks.
Results show status, time, memory, output, and a concise translated error. Drafts never
contain credentials and can be cleared from the editor.
