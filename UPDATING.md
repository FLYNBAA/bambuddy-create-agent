# BCA 更新指南

[English](UPDATING.en.md) | **中文**

本指南适用于 `bambuddy-create-agent` 二次开发仓库。不要按照 upstream Bambuddy 仓库 URL、历史版本 tag 或 upstream 安装脚本更新；它们不包含 BCA 代码、文档和配置契约。

## 更新前必须备份

更新前创建同一恢复点：

```text
DATA_DIR
Bambuddy 原生数据库（SQLite + WAL，或 PostgreSQL dump）
bca_creator_* 明文 Provider 配置
必要的部署环境配置
```

`bca_tasks` 与 `bca_creator_*` 存于原生数据库，BCA 会话与产物存于 `DATA_DIR`。必须使用匹配快照恢复两者。

## 从 Git 工作树更新

在 BCA 仓库根目录：

```bash
# 先确认当前工作树和远程都是你的 BCA fork
pwd
git remote -v
git status

# 拉取并审查要合入的 BCA fork 提交
# 不要盲目 hard reset 未提交的部署改动。
git fetch origin
git log --oneline HEAD..origin/main

# 在确认无需要保留的本地改动后更新
# 分支名按你的 fork 实际分支替换。
git merge --ff-only origin/main
```

然后更新依赖并构建：

```bash
.venv/bin/python -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
npm --prefix .\frontend ci
npm --prefix .\frontend run build
```

启动时数据库迁移由应用执行。更新后检查：

```text
GET /health
GET /api/v1/creator/config
```

`/api/v1/creator/config` 返回明文 Provider 值，只允许具备 `SETTINGS_UPDATE` 的受控管理员浏览器访问；只读状态/API Key 不得读取，响应为 `private, no-store`。

## Docker 更新

从 BCA 仓库根目录：

```bash
# 先备份数据和数据库
# 然后使用当前 BCA checkout 构建，而不是拉 upstream 镜像。
docker compose --env-file .env.bca build
docker compose --env-file .env.bca up -d
docker compose ps
docker compose logs -f bambuddy
```

Windows Docker Desktop：

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml build
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d
curl http://127.0.0.1:8012/health
```

正常停止用：

```bash
docker compose down
```

不要在已有数据的环境中使用 `docker compose down -v`；它会删除命名数据卷。只有明确可丢弃的 smoke 测试栈才允许使用。

## 更新后验证

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_creator_config_api.py -q
.\.venv\Scripts\ruff.exe check backend\app backend\tests
npm --prefix .\frontend run lint
npm --prefix .\frontend run build
```

生产运行验证：

1. 打开 `/creator/settings`，确认 Provider 参数和明文凭据按预期恢复。
2. 检查 `/tasks`，确认任务清单与切片交接状态存在。
3. 检查打印机与原生队列页面。
4. 不要通过更新后自动运行付费 Provider；按 [部署指南](DEPLOYMENT_BCA.zh-CN.md) 的批准 smoke 策略执行。

## 回滚

1. 停止当前进程/容器。
2. 检出或构建已知可用的 BCA 版本。
3. 将数据库和 `DATA_DIR` 同时恢复到同一备份点。
4. 使用受控管理员访问确认 Agent Services 配置和 Provider 凭据。
5. 启动后检查 `/health`、creator、tasks 和原生队列。

## 相关文档

- [中文 README](README.md)
- [中文部署指南](DEPLOYMENT_BCA.zh-CN.md)
- [中文工程契约](AGENTS.zh-CN.md)
