@echo off
setlocal
cd /d "%~dp0"
title EasyOJ

rem ASCII-only on purpose; see the note in the start script.

set "EASYOJ_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%EASYOJ_PY%" (
    echo.
    echo   EasyOJ is not installed yet, so there is nothing to stop.
    echo.
    timeout /t 5 >nul 2>&1
    exit /b 0
)

"%EASYOJ_PY%" "%~dp0scripts\launcher.py" stop
timeout /t 5 >nul 2>&1
exit /b 0
