# Windows LAN Deployment

[English](WINDOWS_DEPLOYMENT_EN.md) · 中文

This deployment profile is for one ordinary Windows desktop serving a trusted
school LAN. It is not a replacement for a VM or a hardened public-internet
service. Do not run the machine with an administrator account for day-to-day
OJ administration, and do not expose port 5000 to the public Internet.

## First installation

Run PowerShell from the project root. If a project `.venv` does not exist, one
Python installation is needed only to bootstrap it; all application packages,
the embedded Python runtime used by submissions, MinGW, and JDK are then kept
under the project directory. The `.venv` runs the web application; it is not
used as the untrusted submission interpreter.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe scripts\deploy\windows\deploy_gui.py
```

Choose `Initialize / repair`. The assistant creates `.env`, `data/`, the
project-local virtual environment dependencies, and the local compiler
toolchain. It is safe to run again; it does not change the system PATH. The
older `setup_toolchain.ps1` remains available for toolchain/runtime-only repair.
Initialization also installs the built-in 30-problem catalog and its 300 test
points; repeating it updates the catalog without duplicating problems.
Student usernames must be 3–32 characters: lowercase letters, numbers, `.`,
`-`, or `_`. The register form states this next to the username field.
The CodeMirror editor is already compiled under
`app/static/vendor/codemirror/`; deployment does not download editor code or
require Node.js. Node and pnpm are developer-only tools for rebuilding those
checked-in static assets.

## Start and operate

```powershell
.\scripts\deploy\windows\start_easyoj.ps1
```

Or double-click **启动 EasyOJ.bat**. Stop with **停止 EasyOJ.bat**.

Production mode uses Waitress, binds to `0.0.0.0:5000` for the LAN, and starts
one judge worker per logical CPU unless `MAX_JUDGE_WORKERS` is set. Set
`EASYOJ_HOST=127.0.0.1` when testing locally. The service does not bind ports
80 or 443 (those need administrator rights and TLS). The launcher prints
`0.0.0.0:5000` plus RFC1918 classroom URLs; it ignores loopback, link-local,
Cloudflare WARP (`198.18.0.0/15`), CGNAT (`100.64.0.0/10`), and virtual
adapters such as Hyper-V / Docker / WSL when a physical NIC exists. Restrict the
Windows Firewall rule to the school subnet.

The production judge requires Windows AppContainer plus Job Objects. If either
the required Windows capability or the local toolchain is unavailable, code is
rejected instead of running unsandboxed. Never set `JUDGE_REQUIRE_SANDBOX=0`
for untrusted student submissions.

Each submission is capped at 64 KB of source, 64 KB of captured output, 20
seconds of execution, 512 MB of memory, 64 MB of workspace, and 1,024
workspace files. Non-admin accounts are limited to 30 submissions per minute;
the limit is intentionally conservative for a shared classroom machine. The
dispatcher pauses below 1 GB available memory to avoid paging the host to death.
Judge workers and sandboxed submissions run at below-normal priority: they can
still fill idle CPU, but the desktop and web server can preempt them, and a
submission cannot raise itself to HIGH/REALTIME. Set
`JUDGE_HOST_MAX_CPU_PERCENT` below 100 only if you also want dispatch to back
off under CPU load. Queue, global-active, and per-user-active caps reject excess
work before it can exhaust the host. Web practice runs are additionally limited
to one concurrent process by default and five seconds.

## Backup and recovery

Stop the server, copy `data/database.db` and `data/problems/` to an offline
backup, then restart. Keep `.env` private; it contains the session secret.
Initialization prints a one-time temporary password for `admin` in the GUI
deployment log. Save it securely, log in, and change it immediately. You may
set `EASYOJ_INITIAL_ADMIN_PASSWORD` before initialization when a controlled
bootstrap password is required; it must still be changed at first login. Use
the admin reset flow for later temporary passwords. Re-running initialization
also replaces the old known `admin123` seed if it is still active. Reset pages
are marked `no-store` and force the recipient to change the password.

## Safe verification

Classroom installs only have `requirements.txt`, so Ruff and pytest are not
installed. `--safe` checks the local toolchain and the AppContainer sandbox:

```powershell
.\.venv\Scripts\python.exe scripts\verify_windows.py --safe
```

On a development machine with `requirements-dev.txt`, add `--dev` to also run
compileall, Ruff, and pytest:

```powershell
.\.venv\Scripts\python.exe scripts\verify_windows.py --safe --dev
```

Contest rehearsal and the bounded load smoke still use a temporary database:

```powershell
.\.venv\Scripts\python.exe scripts\demo_automated_contest.py --timeout-seconds 20
.\.venv\Scripts\python.exe tests\load\safe_load_test.py --duration 10 --users 4 --workers 2 --max-requests 20
```

The contest rehearsal uses an isolated temporary database, two judge workers,
and five concurrent users. The load command performs bounded GET requests only.
It refuses values above 30 seconds, 12 users, 2 workers, or 100 requests. Judge
stress tests require an explicit operator decision and should never be run
during a class.
