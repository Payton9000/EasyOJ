# Windows Deployment

[中文](README.md) · English

On a school-LAN Windows PC, use the graphical assistant:

```powershell
.\.venv\Scripts\python.exe scripts/deploy/windows/deploy_gui.py
```

Choose **Initialize / repair** on first use. It creates `.venv` in the project
folder, writes `.env`, installs Python dependencies, downloads MinGW/JDK into
`toolchain/` (China mirrors first, official URLs as fallback), and initializes
the database. It does not change the system PATH and does not install compilers
globally. If the project has no Python yet, use the system Python once to create
`.venv`; afterwards the project interpreter runs the service.

Start the service:

```powershell
.\scripts\deploy\windows\start_easyoj.ps1
```

It listens on `0.0.0.0:5000` for the LAN. Restrict the Windows Firewall port to
the trusted school subnet, and change the bootstrap admin password after the
first login.

The older toolchain-only scripts below still work. They assume the project
source is already on disk and only prepare compilers.

See [docs/WINDOWS_DEPLOYMENT_EN.md](../../docs/WINDOWS_DEPLOYMENT_EN.md) for the
full classroom operations guide (sandbox, backup, `--safe` / `--dev`).

## Windows

Script: `scripts/deploy/windows/setup_toolchain.ps1`

What it does:

- Download MinGW + JDK
- Extract under `toolchain/` (legacy layouts used `OJ_System/toolchain`)
- Check that `g++` / `javac` are usable

Usage:

- Default sources:
  - `powershell -ExecutionPolicy Bypass -File scripts/deploy/windows/setup_toolchain.ps1`
- Prefer China mirrors (falls back to official URLs):
  - `powershell -ExecutionPolicy Bypass -File scripts/deploy/windows/setup_toolchain.ps1 -UseChinaMirror`
- Force reinstall:
  - `powershell -ExecutionPolicy Bypass -File scripts/deploy/windows/setup_toolchain.ps1 -UseChinaMirror -Force`

## Linux

Script: `scripts/deploy/linux/setup_toolchain.sh`

- Install g++ (apt/yum)
- Download and extract JDK into `toolchain/jdk`

Usage:

- `bash scripts/deploy/linux/setup_toolchain.sh`
- Prefer China mirrors: `USE_CN_MIRROR=1 bash scripts/deploy/linux/setup_toolchain.sh`

## macOS

Script: `scripts/deploy/macos/setup_toolchain.sh`

- Install g++ (Homebrew)
- Download and extract JDK into `toolchain/jdk`

Usage:

- `bash scripts/deploy/macos/setup_toolchain.sh`
- Prefer China mirrors: `USE_CN_MIRROR=1 bash scripts/deploy/macos/setup_toolchain.sh`

## Notes

- These scripts only prepare the toolchain; they do not fetch project source.
- `toolchain/` is gitignored so binaries stay off the repository.
- Download policy: China mirrors first, then official URLs.
