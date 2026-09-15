# Windows 部署

[English](README_EN.md) · 中文

日用 Windows 机器（学校内网作业/课堂竞赛）推荐使用图形化部署助手：

```powershell
.\.venv\Scripts\python.exe scripts/deploy/windows/deploy_gui.py
```

第一次请双击根目录 **启动 EasyOJ.bat**，在浏览器里完成首次配置。部署助手里的 **Repair toolchain** 只补齐 `.venv` 和编译器，不会创建管理员账号；不会修改系统 PATH，也不会把编译器安装到全局目录。工具链会先测速再从最快的官方源或国内镜像下载。若项目未自带 Python，可仅使用系统 Python 一次创建 `.venv`，之后运行时使用项目内解释器。

启动服务：

```powershell
.\scripts\deploy\windows\start_easyoj.ps1
```

默认监听 `0.0.0.0:5000` 供内网访问。请仅在可信内网开放 Windows 防火墙端口，并首次登录后修改初始化管理员密码。完整教室运维说明见 [docs/WINDOWS_DEPLOYMENT.md](../../docs/WINDOWS_DEPLOYMENT.md)（沙箱、备份、`--safe` / `--dev`）。

以下旧脚本仍可单独使用，仅负责下载本地工具链：

这些脚本默认假设项目代码已经在本机，只负责准备 toolchain。

## Windows

脚本：`scripts/deploy/windows/setup_toolchain.ps1`

功能：
- 下载 MinGW + JDK
- 解压到 `toolchain/`
- 检查 `g++` / `javac` 是否可用

用法：
- 默认源：
  - `powershell -ExecutionPolicy Bypass -File scripts/deploy/windows/setup_toolchain.ps1`
- 国内镜像优先（自动回退官方源）：
  - `powershell -ExecutionPolicy Bypass -File scripts/deploy/windows/setup_toolchain.ps1 -UseChinaMirror`
- 强制重装：
  - `powershell -ExecutionPolicy Bypass -File scripts/deploy/windows/setup_toolchain.ps1 -UseChinaMirror -Force`

## Linux

脚本：`scripts/deploy/linux/setup_toolchain.sh`

功能：
- 安装 g++（apt/yum）
- 下载并解压 JDK 到 `toolchain/jdk`

用法：
- `bash scripts/deploy/linux/setup_toolchain.sh`
- 国内镜像优先：
  - `USE_CN_MIRROR=1 bash scripts/deploy/linux/setup_toolchain.sh`

## macOS

脚本：`scripts/deploy/macos/setup_toolchain.sh`

功能：
- 安装 g++（Homebrew）
- 下载并解压 JDK 到 `toolchain/jdk`

用法：
- `bash scripts/deploy/macos/setup_toolchain.sh`
- 国内镜像优先：
  - `USE_CN_MIRROR=1 bash scripts/deploy/macos/setup_toolchain.sh`

## 说明

- 脚本仅准备工具链，不会拉取项目代码。
- `toolchain` 已建议加入 `.gitignore`，避免把二进制提交到仓库。
- 下载源策略：国内镜像优先，失败自动回退到官方 URL。
