(function () {
    'use strict';

    function safeStorage(storageName) {
        try {
            var storage = window[storageName];
            var probe = '__easyoj_workspace_probe__';
            storage.setItem(probe, '1');
            storage.removeItem(probe);
            return storage;
        } catch (error) {
            return null;
        }
    }

    function createTextareaAdapter(editor) {
        return {
            isEnhanced: false,
            getValue: function () {
                return editor.value;
            },
            setValue: function (value) {
                editor.value = typeof value === 'string' ? value : '';
            },
            focus: function () {
                editor.focus();
            },
            replaceSelection: function (text) {
                var start = editor.selectionStart;
                var end = editor.selectionEnd;
                if (typeof editor.setRangeText === 'function') {
                    editor.setRangeText(text, start, end, 'end');
                } else {
                    document.execCommand('insertText', false, text);
                }
                editor.dispatchEvent(new Event('input', { bubbles: true }));
            },
            setLanguage: function () {}
        };
    }

    function initWorkspace(workspace) {
        var storage = safeStorage('localStorage');
        var sessionStore = safeStorage('sessionStorage');
        var editor = workspace.querySelector('[data-code-editor]');
        var input = workspace.querySelector('[data-custom-input]');
        var language = workspace.querySelector('[data-language-select]');
        var lineNumbers = workspace.querySelector('[data-line-numbers]');
        var runButton = workspace.querySelector('[data-run-code]');
        var submitButton = workspace.querySelector('[data-submit-code]');
        var form = workspace.querySelector('[data-workspace-form]');
        var result = workspace.querySelector('[data-run-result]');
        var draftStatus = workspace.querySelector('[data-draft-status]');
        var busy = false;
        var draftTimer = null;
        var initialCode = editor ? editor.value : '';
        var currentLanguage = language ? language.value : '';
        var draftScope = workspace.dataset.draftScope || '';
        var editorController;

        if (!editor || !language || !result) {
            return;
        }
        editorController = createTextareaAdapter(editor);

        function getAnonymousScope() {
            var key = 'easyoj:anonymous-draft-scope';
            if (draftScope || !sessionStore) {
                return draftScope || 'anonymous:' + Math.random().toString(36).slice(2);
            }
            try {
                var existing = sessionStore.getItem(key);
                if (existing) {
                    return existing;
                }
                var generated = 'anonymous:' + Math.random().toString(36).slice(2);
                sessionStore.setItem(key, generated);
                return generated;
            } catch (error) {
                return 'anonymous:' + Math.random().toString(36).slice(2);
            }
        }

        draftScope = getAnonymousScope();

        function draftKey() {
            return 'easyoj:draft:' + draftScope + ':' + workspace.dataset.workspaceKey + ':' + currentLanguage;
        }

        function setDraftStatus(message) {
            if (draftStatus) {
                draftStatus.textContent = message;
            }
        }

        function updateLineNumbers() {
            if (!lineNumbers || editorController.isEnhanced) {
                return;
            }
            var count = Math.max(1, editorController.getValue().split('\n').length);
            lineNumbers.textContent = Array.from({ length: count }, function (_, index) {
                return index + 1;
            }).join('\n');
            lineNumbers.scrollTop = editor.scrollTop;
        }

        function persistDraft() {
            if (!storage) {
                return;
            }
            try {
                var value = editorController.getValue();
                if (value) {
                    storage.setItem(draftKey(), value);
                } else {
                    storage.removeItem(draftKey());
                }
                setDraftStatus(workspace.dataset.draftSaved);
            } catch (error) {
                // A full or disabled browser store should not block editing.
            }
        }

        function scheduleDraftSave() {
            if (draftTimer !== null) {
                window.clearTimeout(draftTimer);
            }
            draftTimer = window.setTimeout(function () {
                draftTimer = null;
                persistDraft();
            }, 450);
        }

        function flushDraftSave() {
            if (draftTimer !== null) {
                window.clearTimeout(draftTimer);
                draftTimer = null;
            }
            persistDraft();
        }

        function readSessionValue(key) {
            if (!sessionStore) {
                return null;
            }
            try {
                return sessionStore.getItem(key);
            } catch (error) {
                return null;
            }
        }

        function consumeCompletedSubmission() {
            var completed = readSessionValue('easyoj:submission-complete');
            if (!completed) {
                return;
            }
            try {
                var marker = JSON.parse(completed);
                if (marker.key === draftKey()) {
                    storage.removeItem(draftKey());
                    setDraftStatus(workspace.dataset.draftCleared);
                    sessionStore.removeItem('easyoj:submission-complete');
                    sessionStore.removeItem('easyoj:submission-pending');
                }
            } catch (error) {
                // Ignore malformed session state and keep the user's draft safe.
            }
        }

        function markSubmissionPending() {
            if (!sessionStore) {
                return;
            }
            try {
                sessionStore.setItem('easyoj:submission-pending', JSON.stringify({
                    key: draftKey(),
                    createdAt: Date.now()
                }));
            } catch (error) {
                // Submission must remain usable when sessionStorage is unavailable.
            }
        }

        function expireOldSubmissionMarker() {
            var pending = readSessionValue('easyoj:submission-pending');
            if (!pending || !sessionStore) {
                return;
            }
            try {
                if (Date.now() - JSON.parse(pending).createdAt > 60 * 60 * 1000) {
                    sessionStore.removeItem('easyoj:submission-pending');
                }
            } catch (error) {
                sessionStore.removeItem('easyoj:submission-pending');
            }
        }

        function loadDraft(useInitialCode) {
            var draft = null;
            if (storage) {
                try {
                    draft = storage.getItem(draftKey());
                } catch (error) {
                    draft = null;
                }
            }
            editorController.setValue(draft !== null ? draft : (useInitialCode ? initialCode : ''));
            updateLineNumbers();
        }

        function insertText(text) {
            editorController.replaceSelection(text);
        }

        function indentSelection() {
            var start = editor.selectionStart;
            var end = editor.selectionEnd;
            var value = editorController.getValue();
            var lineStart = value.lastIndexOf('\n', start - 1) + 1;
            var selectedEnd = value.indexOf('\n', end);
            if (selectedEnd === -1) {
                selectedEnd = value.length;
            }
            var selected = value.slice(lineStart, selectedEnd);
            var indented = selected.split('\n').map(function (line) {
                return '    ' + line;
            }).join('\n');
            editor.setRangeText(indented, lineStart, selectedEnd, 'select');
            editor.selectionStart = lineStart;
            editor.selectionEnd = lineStart + indented.length;
            editor.dispatchEvent(new Event('input', { bubbles: true }));
        }

        function setBusy(value, stateText) {
            busy = value;
            result.setAttribute('aria-busy', value ? 'true' : 'false');
            if (runButton) {
                var runDisabled = value || workspace.dataset.authenticated !== 'true';
                runButton.disabled = runDisabled;
                runButton.setAttribute('aria-disabled', runDisabled ? 'true' : 'false');
            }
            if (submitButton) {
                var submitDisabled = value || workspace.dataset.authenticated !== 'true';
                submitButton.disabled = submitDisabled;
                submitButton.setAttribute('aria-disabled', submitDisabled ? 'true' : 'false');
            }
            if (stateText) {
                result.querySelector('[data-result-status]').textContent = stateText;
            }
        }

        function showResult(payload, failed) {
            var data = payload && payload.result ? payload.result :
                (payload && payload.data ? payload.data : (payload || {}));
            var output = data.output || data.stdout || '';
            var error = data.error || data.message || '';
            var status = data.status || '';
            var localizedStatus = statusLabels[status] || status;
            result.querySelector('[data-result-status]').textContent = localizedStatus || (failed ? workspace.dataset.requestFailed : workspace.dataset.ready);
            result.querySelector('[data-result-panel="output"]').textContent = output || error || localizedStatus || workspace.dataset.ready;
            result.querySelector('[data-summary-status]').textContent = localizedStatus || '-';
            result.querySelector('[data-summary-time]').textContent = data.time_used == null ? '-' : data.time_used + ' ms';
            result.querySelector('[data-summary-memory]').textContent = data.memory_used == null ? '-' : data.memory_used + ' KB';
            result.querySelector('[data-summary-error]').textContent = error || '-';
            result.dataset.state = failed ? 'error' : 'success';
        }

        var statusLabels = {
            Pending: workspace.dataset.statusPending,
            Queued: workspace.dataset.statusQueued,
            Judging: workspace.dataset.statusJudging,
            AC: workspace.dataset.statusAc,
            WA: workspace.dataset.statusWa,
            CE: workspace.dataset.statusCe,
            RE: workspace.dataset.statusRe,
            TLE: workspace.dataset.statusTle,
            MLE: workspace.dataset.statusMle,
            OLE: workspace.dataset.statusOle,
            Failed: workspace.dataset.statusFailed,
            SystemError: workspace.dataset.statusSystemError,
            OK: workspace.dataset.statusOk,
            Busy: workspace.dataset.statusBusy,
            Invalid: workspace.dataset.statusInvalid
        };

        function runCode() {
            if (busy || workspace.dataset.authenticated !== 'true') {
                return;
            }
            var runUrl = workspace.dataset.runUrl;
            if (!runUrl) {
                showResult({ status: workspace.dataset.runUnavailable }, true);
                return;
            }
            setBusy(true, workspace.dataset.running);
            fetch(runUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': workspace.dataset.csrfToken
                },
                body: JSON.stringify({ language: language.value, code: editorController.getValue(), input: input ? input.value : '' })
            }).then(function (response) {
                return response.json().then(function (payload) {
                    return { ok: response.ok, payload: payload };
                });
            }).then(function (response) {
                showResult(response.payload, !response.ok);
            }).catch(function () {
                showResult({ status: workspace.dataset.requestFailed }, true);
            }).finally(function () {
                setBusy(false);
            });
        }

        if (window.EasyOJEditor && typeof window.EasyOJEditor.mount === 'function') {
            var enhancedEditor = window.EasyOJEditor.mount(editor, {
                language: currentLanguage,
                onRun: runCode,
                onSubmit: function () {
                    if (form && submitButton && !submitButton.disabled) {
                        form.requestSubmit(submitButton);
                    }
                }
            });
            if (enhancedEditor) {
                editorController = enhancedEditor;
            }
        }

        editor.addEventListener('input', function () {
            updateLineNumbers();
            scheduleDraftSave();
        });
        editor.addEventListener('scroll', updateLineNumbers);
        editor.addEventListener('keydown', function (event) {
            if (event.key === 'Tab') {
                event.preventDefault();
                if (editor.selectionStart === editor.selectionEnd) {
                    insertText('    ');
                } else {
                    indentSelection();
                }
            } else if (event.ctrlKey && event.key === 'Enter') {
                event.preventDefault();
                if (event.shiftKey && form && submitButton && !submitButton.disabled) {
                    form.requestSubmit(submitButton);
                } else {
                    runCode();
                }
            }
        });
        language.addEventListener('change', function () {
            flushDraftSave();
            currentLanguage = language.value;
            editorController.setLanguage(currentLanguage);
            loadDraft(false);
            setDraftStatus(workspace.dataset.ready);
        });
        if (runButton) {
            runButton.addEventListener('click', runCode);
        }
        if (form) {
            form.addEventListener('submit', function (event) {
                if (busy) {
                    event.preventDefault();
                    return;
                }
                editor.value = editorController.getValue();
                flushDraftSave();
                markSubmissionPending();
                setBusy(true, workspace.dataset.submitting);
            });
        }
        workspace.querySelectorAll('[data-clear-draft]').forEach(function (button) {
            button.addEventListener('click', function () {
                if (draftTimer !== null) {
                    window.clearTimeout(draftTimer);
                    draftTimer = null;
                }
                if (storage) {
                    try {
                        storage.removeItem(draftKey());
                    } catch (error) {
                        // Keep the clear action useful even when storage is unavailable.
                    }
                }
                editorController.setValue('');
                updateLineNumbers();
                setDraftStatus(workspace.dataset.draftCleared);
                editorController.focus();
            });
        });
        var resultTablist = workspace.querySelector('[role="tablist"]');
        var resultTabs = Array.from(workspace.querySelectorAll('[data-result-tab]'));

        function activateResultTab(tab, moveFocus) {
            var selected = tab.dataset.resultTab;
            resultTabs.forEach(function (item) {
                var active = item === tab;
                item.classList.toggle('is-active', active);
                item.setAttribute('aria-selected', active ? 'true' : 'false');
                item.setAttribute('tabindex', active ? '0' : '-1');
            });
            workspace.querySelectorAll('[data-result-panel]').forEach(function (panel) {
                panel.hidden = panel.dataset.resultPanel !== selected;
            });
            if (resultTablist) {
                resultTablist.setAttribute('aria-activedescendant', tab.id);
            }
            if (moveFocus) {
                tab.focus();
            }
        }

        resultTabs.forEach(function (tab, index) {
            tab.addEventListener('click', function () {
                activateResultTab(tab, false);
            });
            tab.addEventListener('keydown', function (event) {
                var nextIndex = index;
                if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
                    nextIndex = (index + resultTabs.length - 1) % resultTabs.length;
                } else if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
                    nextIndex = (index + 1) % resultTabs.length;
                } else if (event.key === 'Home') {
                    nextIndex = 0;
                } else if (event.key === 'End') {
                    nextIndex = resultTabs.length - 1;
                } else {
                    return;
                }
                event.preventDefault();
                activateResultTab(resultTabs[nextIndex], true);
            });
        });

        expireOldSubmissionMarker();
        consumeCompletedSubmission();
        loadDraft(true);
    }

    document.querySelectorAll('[data-coding-workspace]').forEach(initWorkspace);
}());
