# EasyOJ

EasyOJ is a small Flask online judge for a trusted school LAN: programming
assignments, classroom contests, and local practice. The interface follows a
restrained LeetCode-style workspace, supports Chinese and English UI text, and
lets signed-in users run C++, Java, or Python directly from a problem page.
Initialization installs a reviewed 30-problem catalog with 10 test points per
problem.

## Recommended Windows deployment

Run PowerShell from the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe scripts\deploy\windows\deploy_gui.py
```

Choose **Initialize / repair** in the Tkinter window. It creates the project
data directories, installs Python packages into `.venv`, and downloads the
project-local MinGW, JDK, and embedded Python submission runtime. It does not
modify the system `PATH` or require global compilers. It also initializes the
database and built-in problem bank.

Start the LAN service with:

```powershell
.\scripts\deploy\windows\start_easyoj.ps1
```

Open `http://<host-ip>:5000` from the classroom network. Restrict the Windows
Firewall rule to the school subnet; do not expose this profile to the public
Internet. Initialization prints a one-time temporary password for the `admin`
account; save it securely and change it at first login.

See [docs/WINDOWS_DEPLOYMENT.md](docs/WINDOWS_DEPLOYMENT.md) for backup,
firewall, sandbox, and recovery details.

## Safety model

Production judging fails closed unless Windows AppContainer and Job Objects
are available. Each process has CPU time, memory, process-count, output,
workspace-size, workspace-file, and timeout limits. Submissions use absolute
project-local command paths and `shell=False`; network access is not granted
to AppContainer processes. Judge workers use at most half the logical CPUs and
are hard-capped at four. Queue admission limits, per-user active limits, and a
host CPU/memory guard prevent a classroom desktop from being overwhelmed.

## Development and verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app scripts tests problem_bank
.\.venv\Scripts\python.exe scripts\verify_windows.py --safe
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
