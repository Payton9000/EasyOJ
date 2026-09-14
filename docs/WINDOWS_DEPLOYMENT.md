# Windows 局域网部署

[English](WINDOWS_DEPLOYMENT_EN.md) · 中文

本部署方案面向一台普通 Windows 电脑、服务可信的学校局域网。它不能代替虚拟机或面向公网加固的服务。日常管理 OJ 时不要使用管理员账户登录 Windows，也不要把 5000 端口暴露到公网。

## 首次安装

在项目根目录打开 PowerShell。如果还没有项目内的 `.venv`，只需要本机有一份 Python 用来创建它；之后应用依赖、学生提交用的嵌入式 Python、MinGW 和 JDK 都放在项目目录里。`.venv` 只运行网站，不用来执行不受信任的学生代码。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe scripts\deploy\windows\deploy_gui.py
```

选择 **Initialize / repair**。助手会创建 `.env`、`data/`、项目内虚拟环境依赖和本地编译器工具链。可以重复执行；不会修改系统 PATH。仅修复工具链时，仍可使用旧的 `setup_toolchain.ps1`。
初始化同时导入内置 **30** 道题（每题 10 个测试点，共 300 组）；再次执行会更新题库而不会重复建题。
学生用户名必须是 **3–32** 个字符，仅限小写字母、数字、`.`、`-` 或 `_`；注册页用户名旁有说明。
CodeMirror 编辑器已经编译在 `app/static/vendor/codemirror/`，部署不需要下载编辑器代码，也不需要 Node.js。Node 和 pnpm 只给开发者重建这些已入库的静态资源。

也可以双击根目录的 **启动 EasyOJ.bat**：首次运行会走同样的准备流程并弹出设置向导。

## 启动与日常运行

```powershell
.\scripts\deploy\windows\start_easyoj.ps1
```

或双击 **启动 EasyOJ.bat**。停止服务用 **停止 EasyOJ.bat**。

生产模式使用 Waitress，监听 `0.0.0.0:5000` 供局域网访问，并默认按逻辑 CPU 数量启动判题 Worker（可用 `MAX_JUDGE_WORKERS` 限制）。本机自测时可设 `EASYOJ_HOST=127.0.0.1`。服务**不会**绑定 80 或 443（需要管理员权限和 TLS）。启动器会打印 `0.0.0.0:5000` 以及 RFC1918 教室地址；会忽略回环、链路本地、Cloudflare WARP（`198.18.0.0/15`）、CGNAT（`100.64.0.0/10`），并且在已有物理网卡时忽略 Hyper-V / Docker / WSL 虚拟网卡。请把 Windows 防火墙规则限制在校园网段。

生产判题要求 Windows AppContainer 和 Job Object。任一能力或本地工具链缺失时，代码会被拒绝执行，而不会在无沙箱下降级运行。对学生提交不要设置 `JUDGE_REQUIRE_SANDBOX=0`。

每份提交限制：源码 64 KB、捕获输出 64 KB、运行 20 秒、内存 512 MB、工作区 64 MB、工作区文件 1024 个。非管理员每分钟最多 30 次提交，这是共享教室机上的保守值。可用内存低于 1 GB 时调度器会暂停，避免把主机换到死机。判题 Worker 和沙箱进程以低于正常的优先级运行：空闲时仍可占满 CPU，桌面和网站需要时可以抢占；提交无法把自己提升到 HIGH/REALTIME。只有在你还希望 CPU 高负载时暂停调度，才把 `JUDGE_HOST_MAX_CPU_PERCENT` 设到 100 以下。队列、全局并发和每用户并发上限会在耗尽主机前拒掉多余任务。网页练习运行默认再限制为同时 1 个进程、5 秒。

## 备份与恢复

先停服务，把 `data/database.db` 和 `data/problems/` 拷到离线备份，再启动。`.env` 含会话密钥，不要公开。
初始化会在部署日志里打印 `admin` 的一次性临时密码，请保存并在首次登录时修改。需要受控的初始密码时可先设置 `EASYOJ_INITIAL_ADMIN_PASSWORD`，首次登录仍必须改密。之后用管理后台重置流程发放临时密码。再次初始化还会替换仍然有效的旧种子密码 `admin123`。重置页标记为 `no-store`，并强制对方下次改密。

## 安全验证

教室安装的 `.venv` 只含 `requirements.txt`，没有 Ruff 和 pytest。`--safe` 只检查本地工具链和 AppContainer 沙箱：

```powershell
.\.venv\Scripts\python.exe scripts\verify_windows.py --safe
```

开发机装了 `requirements-dev.txt` 时，加上 `--dev` 才会跑 compileall、Ruff 和 pytest：

```powershell
.\.venv\Scripts\python.exe scripts\verify_windows.py --safe --dev
```

竞赛演练和有界负载测试使用临时数据库：

```powershell
.\.venv\Scripts\python.exe scripts\demo_automated_contest.py --timeout-seconds 20
.\.venv\Scripts\python.exe tests\load\safe_load_test.py --duration 10 --users 4 --workers 2 --max-requests 20
```

竞赛演练使用隔离的临时库、两个判题 Worker、五个并发用户。负载命令只做有界 GET，超过 30 秒、12 用户、2 Worker 或 100 请求会被拒绝。判题压测需要运维明确决定，上课期间不要跑。
