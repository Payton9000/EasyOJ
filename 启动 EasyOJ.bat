@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title EasyOJ

rem Deliberately ASCII-only. A UTF-8 batch file combined with "chcp 65001" makes
rem cmd mis-parse its own lines, which produced errors like "'_PY' is not
rem recognized". User-facing Chinese text lives in the Python launcher instead.

set "EASYOJ_PY=%~dp0.venv\Scripts\python.exe"
if exist "%EASYOJ_PY%" goto run

rem First run only: borrow a system Python long enough to build the project venv.
where py >nul 2>&1
if not errorlevel 1 (
    set "EASYOJ_PY=py"
    set "EASYOJ_PYARG=-3"
    goto run
)
where python >nul 2>&1
if not errorlevel 1 (
    set "EASYOJ_PY=python"
    set "EASYOJ_PYARG="
    goto run
)

echo.
echo   Python 3.10 or newer is required, and none was found.
echo.
echo   1. Open https://www.python.org/downloads/
echo   2. During setup, tick "Add python.exe to PATH"
echo   3. Double-click this file again
echo.
pause
exit /b 1

:run
"%EASYOJ_PY%" %EASYOJ_PYARG% "%~dp0scripts\launcher.py" start
if errorlevel 1 (
    echo.
    echo   Startup failed. Please show the message above to your administrator.
    echo.
    pause
    exit /b 1
)

rem Keep the address on screen briefly before the window closes.
timeout /t 8 >nul 2>&1
exit /b 0
