# EasyOJ 系统说明

EasyOJ 是一个基于 Flask 的在线判题系统，支持 C++、Java、Python 三种提交语言，包含题目管理、提交判题、竞赛功能、后台管理与接口访问。

## 主要特性

- 在线提交与判题
- 多语言支持：C++ / Java / Python
- 判题结果：AC、WA、TLE、MLE、RE、CE
- 判题任务队列、重试、超时回收、日志落盘
- 普通用户竞赛页面（报名、题目、提交、排行榜）
- 管理后台（用户、题目、竞赛、提交、判题监控）
- 多进程判题 Worker（可按 CPU 核心自动扩展）

## 技术栈

- Python 3.11+
- Flask
- Flask-SQLAlchemy
- Flask-Login
- Flask-Migrate
- SQLite（默认）

## 项目结构

- app/: 核心应用代码（模型、路由、判题引擎、模板）
- data/: 数据库存储、题目测试数据、提交目录
- toolchain/: 本地工具链目录（运行时下载，不建议入库）
- tests/: 单元、集成、端到端、压力测试
- scripts/deploy/: 工具链部署脚本（Windows/Linux/macOS）
- run.py: 应用启动入口
- init_db.py: 初始化数据库、默认管理员、示例题

## 快速开始（本机已有代码）

### 1) 创建并激活虚拟环境

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2) 安装依赖

```bash
pip install -r requirements.txt
```

### 3) 安装工具链（推荐）

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/deploy/windows/setup_toolchain.ps1 -UseChinaMirror
```

Linux:

```bash
USE_CN_MIRROR=1 bash scripts/deploy/linux/setup_toolchain.sh
```

macOS:

```bash
USE_CN_MIRROR=1 bash scripts/deploy/macos/setup_toolchain.sh
```

### 4) 初始化数据库

```bash
python init_db.py
```

默认管理员账号：

- 用户名：admin
- 密码：admin123

### 5) 启动系统

```bash
python run.py development
```

默认访问地址：

- http://127.0.0.1:5000

## 部署配置建议

### 判题 Worker 数量

系统支持按 CPU 自动设置 Worker 数量：

- 默认逻辑：max(1, CPU核心数 - 1)
- 可通过环境变量手动覆盖

```powershell
$env:MAX_JUDGE_WORKERS="8"
python run.py development
```

### Flask 并发模式（开发环境）

默认开启 threaded。可通过环境变量关闭：

```powershell
$env:FLASK_THREADED="0"
python run.py development
```

## API 概览

- GET /api/problems
- GET /api/problems/<problem_id>
- POST /api/submit/<problem_id>
- GET /api/submission/<submission_id>
- GET /api/submissions
- GET /api/ranking

## 测试

### 全量自动化测试

```bash
python -m pytest -q
```

### 压力测试（soak）

```bash
python -u tests/load/soak_test.py --duration 300 --interval 0.2 --report-every 30 --users 12 --workers 4 --problems-per-size 5 --poll-timeout 120
```

输出包括：

- 提交数量
- 失败数量
- 队列长度
- CPU/内存/句柄
- 判题状态分布
- mismatch 样本

## 常见问题

### 1) 提示 compiler not found

先执行 scripts/deploy 下对应系统脚本安装工具链，再重启服务。

### 2) 运行压力测试出现 Queued/Judging 比例较高

通常是提交速率高于判题吞吐：

- 提高 MAX_JUDGE_WORKERS
- 降低 users 或加大 interval
- 提高 poll-timeout

### 3) 工具链是否应提交到 Git

不建议。toolchain 属于运行时依赖，应通过部署脚本在目标机器下载。

## 安全提示

- 请在生产环境设置强随机 SECRET_KEY
- 默认管理员密码仅用于初始化，请首次登录后立刻修改
- 开发服务器不建议直接用于生产
