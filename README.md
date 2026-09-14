# EasyOJ

[English](README_EN.md) · 中文

EasyOJ 是一个基于 Flask 的轻量级在线评测系统，面向学校局域网环境。支持编程作业布置、课堂竞赛和本地练习。界面提供中英文切换，登录用户可以从题目页面直接运行 C++、Java 或 Python 代码。首次运行自动导入内置题库（30 道题，每题 10 个测试点）。

## 快速开始

双击项目根目录下的 **启动 EasyOJ.bat**。

首次运行会自动完成所有准备工作：创建项目内的 `.venv` 虚拟环境、安装本地的 MinGW、JDK 和 Python 提交运行时，生成 `SECRET_KEY`，初始化数据库和内置题库。全程不需要修改系统 `PATH`，不需要预装全局编译器。网络较慢时首次启动需要较长时间，之后每次启动直接进入服务状态并打印局域网地址。

首次启动会弹出设置向导，填写以下信息：

| 设置项 | 说明 |
| --- | --- |
| 管理员用户名和密码 | 登录后台的凭据，自行设置后不会打印或丢失。 |
| 站点名称 | 显示在页面标题和导航栏，例如班级名或学校名。 |
| 端口 | 默认 5000；若该端口被占用，向导会自动建议其他端口。 |

学生自行注册时，用户名必须是 **3–32** 个字符，仅限小写字母、数字、`.`、`-` 或 `_`。

没有桌面环境时（例如通过 SSH 远程访问），相同的信息以命令行问答形式呈现。所有配置保存在 `.env` 文件中，后续可直接编辑修改。

服务启动后会在后台运行，关闭窗口不会停止。双击 **停止 EasyOJ.bat** 可停止服务。只需系统中安装了 Python 3.10 或更高版本；启动器会在缺失时自动提示安装方式。

## 部署助手（可选）

如需开机自启、自动备份和通知区图标：

```powershell
.\.venv\Scripts\python.exe scripts\deploy\windows\deploy_gui.py
```

也可以在部署助手窗口中通过 **Initialize / repair** 重新执行初始化。

在同一局域网的其他电脑上打开 `http://<本机IP>:5000` 即可访问。请在 Windows 防火墙中限制为校内网段，不要暴露到公网。初始化完成后会为 `admin` 账户生成一次性临时密码，请妥善保存并在首次登录时修改。

## 后台静默运行

部署助手窗口提供了日常操作控制：

- **开机自启** 在开机登录时自动在后台启动服务，不需要管理员权限。使用 `pythonw.exe` 运行，不会弹出命令行窗口。再次点击可取消自启。
- **最小化到托盘** 将窗口隐藏到通知区而不关闭服务；关闭窗口的行为相同。双击通知区图标可恢复窗口。
- **立即备份** 立刻生成一次数据库备份。

服务还会自动备份：启动时备份一次（距上次不足 20 小时则跳过），之后每天备份一次。备份保存在 `data/backups/` 目录，最多保留 14 份。备份使用 SQLite `VACUUM INTO`，服务运行中无需停机，且备份文件一致可靠。**直接复制 `database.db` 并不等价**——在 WAL 模式下，已提交的数据分散在数据库文件和 `-wal` 侧车文件中。

如偏好命令行，等价操作：

```powershell
.\.venv\Scripts\python.exe scripts\deploy\windows\autostart.py status
.\.venv\Scripts\python.exe scripts\deploy\windows\autostart.py enable
.\.venv\Scripts\python.exe scripts\deploy\windows\autostart.py disable
.\.venv\Scripts\python.exe scripts\backup_now.py
```

也可以通过 `autostart.py enable --method scheduled-task` 注册为计划任务，这样服务在任何人登录前就会启动，但需要管理员权限运行。

管理后台的 **判题状态** 页面显示服务运行状况——判题引擎状态、运行时长、待评测数量以及上次备份时间。无窗口启动的日志记录在 `data/logs/service.log` 中。

详见 [docs/WINDOWS_DEPLOYMENT.md](docs/WINDOWS_DEPLOYMENT.md) 了解备份、防火墙、沙箱和故障恢复的详细说明。

## 安全模型

生产环境的判题在 Windows AppContainer 和 Job Object 不可用时会拒绝执行（fail-closed）。每个提交进程有 CPU 时间、内存、进程数、输出大小、工作区容量、工作区文件数和超时限制。提交代码使用项目内的绝对路径，禁止网络访问，启动方式为 `shell=False`。判题 Worker 默认每个逻辑 CPU 一个。沙箱进程和 Worker 以低于正常的优先级运行：主机空闲时仍可占满 CPU，桌面和 Web 服务需要时可以抢占，避免卡死；提交无法把自己提升到高优先级。队列准入限制、每用户并发限制和至少 1 GB 可用内存的监控防止内存耗尽导致死机。

## 开发与验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app scripts tests problem_bank
.\.venv\Scripts\python.exe scripts\verify_windows.py --safe --dev
```

导入或修复内置题库，然后进行一场隔离的竞赛演练（5 个用户并发注册和提交）：

```powershell
.\.venv\Scripts\python.exe scripts\seed_problem_bank.py
.\.venv\Scripts\python.exe scripts\demo_automated_contest.py --timeout-seconds 20
```

安全负载测试仅执行有界 GET 请求：

```powershell
.\.venv\Scripts\python.exe tests\load\safe_load_test.py
```

## 前端编辑器资源

题目页面使用项目本地的 CodeMirror 6 编辑器，提供语法高亮、自动补全、代码片段、括号匹配、代码折叠、搜索和多光标编辑功能。`app/static/vendor/codemirror/` 下的生成文件随 EasyOJ 一起分发，正常 Windows 部署不需要 Node.js 或网络连接。

开发者如需重新构建编辑器包，本地需安装 Node.js 20+ 和 pnpm：

```powershell
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend test
pnpm --dir frontend run build
```

请勿将本地资源替换为 CDN 链接；学生提交代码和编辑器流量必须保持在局域网内。

## 新增语言支持

在 `app/judge/languages.py` 中注册参数向量格式的编译/运行配置，在 Windows 部署层添加工具链的绝对路径，并补充单元测试和沙箱安全测试。不要使用 shell 命令字符串拼接，也不要静默降级为无沙箱的生产执行。
