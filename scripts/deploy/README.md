# Toolchain Deploy Scripts

这些脚本默认假设项目代码已经在本机，只负责准备 toolchain。

## Windows

脚本：`scripts/deploy/windows/setup_toolchain.ps1`

功能：
- 下载 MinGW + JDK
- 解压到 `OJ_System/toolchain`
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
