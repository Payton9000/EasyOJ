# EasyOJ

[中文](README.md) · English

EasyOJ is a small Flask online judge for a trusted school LAN: programming
assignments, classroom contests, and local practice. The interface follows a
restrained LeetCode-style workspace, supports Chinese and English UI text, and
lets signed-in users run C++, Java, or Python directly from a problem page.
Initialization installs a reviewed 30-problem catalog with 10 test points per
problem.

## Quick start

Double-click **启动 EasyOJ.bat** in this folder.

The first run installs everything the service needs: a project-local `.venv`, the
project-local MinGW, JDK, and embedded Python submission runtime, a generated
`SECRET_KEY`, and the database with its built-in problem bank. It does not modify
the system `PATH` and does not require globally installed compilers. The first
install speed-tests the official URLs plus several China mirrors, then downloads
MinGW, JDK, and the Python runtime from the fastest source (SHA-256 verified,
then the next-fastest if a checksum fails), about 400 MB in total. A very slow
link can take more than an hour; if the first run is interrupted, double-click
the file again and it resumes the toolchain. Later runs go straight to serving
and print the classroom address.

A short setup window then asks for the things only you can decide:

| Setting | Notes |
| --- | --- |
| Administrator username and password | How you sign in. Choose it yourself so it is never printed or lost. |
| Site name | Shown in the header and page titles, e.g. a class or school name. |
| Port | Defaults to 5000; the wizard suggests another if that one is taken. |

Student usernames must be **3–32** characters: lowercase letters, numbers, `.`,
`-`, or `_`.

Without a desktop session (for example over SSH) the same questions are asked as
text prompts. Everything is stored in `.env` and can be changed later by editing
that file.

The service keeps running after the window closes. Double-click
**停止 EasyOJ.bat** to stop it. Only Python 3.10 or newer needs to be present
beforehand; the launcher explains how to install it if it is missing.

## Deployment assistant (optional)

For auto-start, backups, and a notification-area icon:

```powershell
.\.venv\Scripts\python.exe scripts\deploy\windows\deploy_gui.py
```

The same setup can be re-run from there with **Initialize / repair**.

Open `http://<host-ip>:5000` from the classroom network. Restrict the Windows
Firewall rule to the school subnet; do not expose this profile to the public
Internet. Initialization prints a one-time temporary password for the `admin`
account; save it securely and change it at first login.

## Running unattended

The deployment window has three controls for day-to-day operation:

- **Start with Windows** adds a Startup-folder shortcut so the service comes up in
  the background at sign-in. It needs no administrator rights, and the launcher
  uses `pythonw.exe`, so no console window appears. Press it again to remove.
- **Minimise to tray** hides the window without stopping the server; closing the
  window while the server is running does the same. Double-click the
  notification-area icon to bring it back.
- **Back up now** writes an immediate database snapshot.

The service also backs itself up: once at start-up (skipped when a backup is less
than 20 hours old) and then daily, into `data/backups/`, keeping the newest 14.
Backups use SQLite `VACUUM INTO`, so they are consistent and never require
stopping the service. Copying `database.db` by hand is *not* equivalent — in WAL
mode part of the committed state lives in the `-wal` sidecar file.

Equivalent commands, for anyone who prefers the shell:

```powershell
.\.venv\Scripts\python.exe scripts\deploy\windows\autostart.py status
.\.venv\Scripts\python.exe scripts\deploy\windows\autostart.py enable
.\.venv\Scripts\python.exe scripts\deploy\windows\autostart.py disable
.\.venv\Scripts\python.exe scripts\backup_now.py
```

Automatic startup can also be registered as a Scheduled Task with
`autostart.py enable --method scheduled-task`, which brings the service up before
anyone signs in but must be run from an elevated prompt.

The administrator area reports service health — judging state, uptime, submissions
awaiting judgement, and the age of the last backup — under **Judge status**.
Unattended start-up logs to `data/logs/service.log`.

See [docs/WINDOWS_DEPLOYMENT_EN.md](docs/WINDOWS_DEPLOYMENT_EN.md) (English) or
[docs/WINDOWS_DEPLOYMENT.md](docs/WINDOWS_DEPLOYMENT.md) (中文) for backup,
firewall, sandbox, and recovery details.

## Safety model

Production judging fails closed unless Windows AppContainer and Job Objects
are available. Each process has CPU time, memory, process-count, output,
workspace-size, workspace-file, and timeout limits. Submissions use absolute
project-local command paths and `shell=False`; network access is not granted
to AppContainer processes. Judge workers default to one per logical CPU.
Sandbox jobs and worker processes run at below-normal priority so idle CPU can
be used fully while the desktop and web server stay preemptible, and submissions
cannot raise themselves to HIGH/REALTIME. Queue admission limits, per-user
active limits, and a 1 GiB host memory reserve prevent the machine from
crashing under load.

## Development and verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app scripts tests problem_bank
.\.venv\Scripts\python.exe scripts\verify_windows.py --safe --dev
```

Import or repair the built-in catalog, then rehearse an isolated contest where
five users register and submit concurrently:

```powershell
.\.venv\Scripts\python.exe scripts\seed_problem_bank.py
.\.venv\Scripts\python.exe scripts\demo_automated_contest.py --timeout-seconds 20
```

The safe load test performs bounded GET requests only:

```powershell
.\.venv\Scripts\python.exe tests\load\safe_load_test.py
```

## Browser editor assets

Problem pages use a project-local CodeMirror 6 bundle with syntax highlighting,
completion, snippets, brackets, folding, search, and multi-cursor editing. The
generated files under `app/static/vendor/codemirror/` are shipped with EasyOJ,
so normal Windows deployment does not need Node.js or an internet connection.

Contributors rebuilding the bundle use Node.js 20+ and pnpm locally:

```powershell
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend test
pnpm --dir frontend run build
```

Do not replace the local assets with CDN links; student source and editor
traffic must remain inside the LAN.

## Adding languages

Register an argument-vector specification in `app/judge/languages.py`, add
absolute toolchain paths in the Windows deployment layer, and add unit plus
judge-safety tests. Do not build shell command strings or silently fall back
to unsandboxed production execution.
