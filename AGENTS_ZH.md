# 仓库协作说明

[English](AGENTS.md) · 中文

## 项目结构

EasyOJ 是面向可信学校局域网的 Windows 优先 Flask 在线评测系统。应用代码在 `app/`：路由在 `app/web/` 和 `app/api/`，判题在 `app/judge/`，模板和静态资源在 `app/templates/` 与 `app/static/`。CodeMirror 源码和测试在 `frontend/`；生成的编辑器资源在 `app/static/vendor/codemirror/`，`frontend/node_modules/` 不入库。内置题库在 `problem_bank/`；运行时测试点在 `data/problems/<id>/testcases/<n>.in` 和 `<n>.out`。测试按 `tests/unit/`、`tests/integration/`、`tests/e2e/` 和有界的 `tests/load/` 分组。

## 构建、测试与开发命令

在 Windows 上使用项目内环境：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe init_db.py
.venv\Scripts\python.exe run.py development
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check app scripts tests problem_bank
.venv\Scripts\ruff.exe format --check app scripts tests problem_bank
.venv\Scripts\python.exe scripts\verify_windows.py --safe
.venv\Scripts\python.exe scripts\verify_windows.py --safe --dev
pnpm --dir frontend test
pnpm --dir frontend run build
```

`init_db.py` 会创建数据库并导入 30 道内置题。用 `scripts/seed_problem_bank.py` 可幂等修复/重新导入该题库。教室 `--safe` 验证只检查工具链和 AppContainer 冒烟；`--dev` 才会跑 compileall、Ruff 和 pytest。

## 编码风格与命名

目标 Python 3.10，四空格缩进，每行不超过 100 字符，单引号，导入由 Ruff 管理。函数/模块用 `snake_case`，类用 `PascalCase`，路由和服务名要能看出用途。语言命令必须是参数向量，不要拼 shell 命令字符串。界面文案要同时写进 `app/i18n/catalogs.py` 的两套词典；题面仍是数据库里的单语言内容。

## 测试约定

测试文件命名 `test_<behavior>.py`，先写最窄的用例。开发时先跑针对性测试，再跑全套。凡是改判题、账号、竞赛或沙箱，都要有失败路径测试。未经运维明确决定，不要跑 `tests/load/soak_test.py` 或手工压测工具。

## 提交与 Pull Request

本检出可能没有完整 Git 历史。提交说明用简短祈使句，例如 `Fix judge admission race`。Pull request 要说明用户影响、列出验证命令、关联 issue；可见的界面改动要附截图。

## 安全与配置

保持 AppContainer 和 Job Object 的 fail-closed 执行。不要提交 `.env`、数据库文件、临时密码或学生提交。工具链放在项目本地，不要把生产配置暴露到公网。
