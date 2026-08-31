# BCA 部署指南

[English](DEPLOYMENT_BCA.md) | **中文**

本文面向部署和运维开发者。BCA 是 Bambuddy 的内嵌模块，使用同一个 FastAPI 进程、数据库和静态前端，不要把它部署成第二个独立 create-agent 服务。

## 1. 部署前条件

| 条件 | 说明 |
|---|---|
| Python | 本地开发使用 Python 3.11+ 与项目 `.venv`。 |
| Node.js | 仅在本地构建前端时需要；Docker 多阶段构建会处理前端。 |
| Docker | Linux 生产或 Windows Docker Desktop 使用 Docker Compose。 |
| 网络 | Linux host networking 最适合发现、Virtual Printer、相机与打印机 LAN 协议。 |
| 认证 | 暴露到公网或 Tailnet 时必须启用 Bambuddy 认证和 API Key 管理。 |
| 数据库 | SQLite 支持单机；外部 PostgreSQL 支持必须纳入备份与恢复流程。 |

## 2. Windows 本地开发

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
npm --prefix .\frontend ci
npm --prefix .\frontend run build
$env:DATA_DIR = "$PWD\data"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

首次运行使用 Setup 创建管理员或按你的策略启用认证。不要使用多 Uvicorn worker；BCA 会话锁和后台阶段当前是单进程模型。

## 3. Linux Docker

从仓库根目录执行：

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f bambuddy
```

默认 Linux Compose 使用 host networking。它是打印机发现、SSDP、Virtual Printer、相机和 LAN FTP/MQTT 的推荐模型。

部署环境至少应配置：

```text
DATA_DIR=/app/data
LOG_DIR=/app/logs
BCA_PUBLIC_BASE_URL=https://bca.example.invalid
```

Provider 凭据可以作为首次启动值通过环境变量注入，也可以在启动后由 Agent Services 页面填写并持久化：

```text
DEEPSEEK_API_KEY
IMAGE_API_KEY
TENCENT_SECRET_ID
TENCENT_SECRET_KEY
MESHY_API_KEY
```

BCA 不会读取 source-project `.env` 或 `.env.local`。`.env.bca.example` 是变量名和默认值参考，不要提交真实凭据。

## 4. Windows Docker Desktop

Docker Desktop 不支持生产 Compose 的 Linux `network_mode: host`。使用仓库的 bridge override：

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml build
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d
curl http://127.0.0.1:8012/health
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml down
```

普通停止使用 `down`。`down -v` 会删除命名数据卷，只能用于明确可丢弃的 smoke 测试栈。

该 override 使用：

```yaml
network_mode: !reset null
ports:
  - "${BCA_DOCKER_PORT:-8012}:8000"
```

不要用空字符串代替 `network_mode`；它会产生 Docker `none` 网络并阻止端口发布。

Bridge 模式限制：

- 使用打印机 LAN IP 手动添加打印机；不支持 SSDP 自动发现。
- Virtual Printer 完整被动 FTP 范围和额外相机/代理能力需要额外端口映射。
- 端口 `8012` 已占用时设置 `BCA_DOCKER_PORT`。

## 5. Agent Services 明文配置

Agent Services (`/creator/settings`) 会读取、填写、持久化并热加载：

```text
DeepSeek API Key / Base URL / Model
Image API Key / Base URL / Model / Quality
Tencent Secret ID / Secret Key / Region
Meshy API Key / Input Mode
BCA Public Base URL
```

实现契约：

```text
GET /api/v1/creator/config → SETTINGS_READ → 明文配置
PUT /api/v1/creator/config → SETTINGS_UPDATE → 数据库保存 + Agent Provider 热重载
Cache-Control: private, no-store
```

明文配置保存在 Bambuddy settings 表的 `bca_creator_*` 行。因此能够读取数据库、数据库备份或 Creator Config API 的主体都能读取凭据。仅在受控管理员浏览器、API 客户端、数据库与备份环境中使用此模式。

Base URL 仍被限制为安全的 LAN-service HTTP(S) 地址；不安全 URL 返回 HTTP `422`。

## 6. Meshy public URL 模式

默认推荐：

```text
MESHY_MODEL_INPUT_MODE=data_uri
```

如果使用：

```text
MESHY_MODEL_INPUT_MODE=public_url
```

则 `BCA_PUBLIC_BASE_URL` 必须是 Meshy 能从公网访问的 HTTPS 地址，并经反向代理公开：

```text
GET /api/v1/creator/sessions/{session_id}/model.glb
```

这是用于 Meshy 拉取 GLB 的高熵能力路由，不会出现在普通 creator 会话快照中。

## 7. 反向代理与公网访问

反向代理必须把同一 origin 的静态前端、`/api/v1` 和 WebSocket 正确转发至 Bambuddy。部署时：

- 使用 HTTPS 终止；`BCA_PUBLIC_BASE_URL` 应是外部 HTTPS origin。
- 只在代理地址可信时配置转发头信任。
- 不要把 Provider 密钥、数据库或 `DATA_DIR` 直接映射到公网。
- Tailscale 只提供网络连通性，不提供应用身份认证；仍应启用 Bambuddy 认证和 API Key 管理。

## 8. 数据与备份

必须把以下内容作为**同一恢复点**备份：

```text
DATA_DIR/bca-agent/  creator sessions and persisted artifacts
DATA_DIR/bca-tasks/  task source files waiting for slicing
DATA_DIR/archive/    archives and Library files
```

以及：

1. Bambuddy 原生数据库：SQLite 数据库及一致的 WAL sidecar，或 `DATABASE_URL` 指向的 PostgreSQL 完整 dump。
2. `bca_creator_*` 明文 Provider 设置：它们位于原生 Bambuddy 数据库中。
3. 首次启动仍需要的部署环境与基础设施配置。

仅恢复 `DATA_DIR` 会缺少 `bca_tasks`、Library/队列关系和 Provider 配置；仅恢复数据库会缺少 BCA 产物。必须恢复匹配的数据库与 `DATA_DIR` 快照。

Provider 签名 URL 不是备份产物；BCA 只公开已经下载、验证和持久化的文件。

## 9. 队列交接

BCA 输出的是模型 3MF，不是可直接打印的 job。root 必须上传 slicer 生成的 `.gcode.3mf`，且包内必须有：

```text
Metadata/plate_N.gcode
Metadata/slice_info.config
```

验证后 BCA 创建原生 `LibraryFile`，再通过 `add_to_queue()` 创建 `manual_start=True` 的原生 `PrintQueueItem`。开始、取消、AMS 映射、打印机状态与归档继续由 Bambuddy 负责。

## 10. 付费 Provider smoke

日常测试不得调用付费 Provider。非计费检查：

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_provider_smoke.py --base-url http://127.0.0.1:8000
```

经过人工批准的完整链路：

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_full_paid_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --confirm-paid `
  --seed-calibration-spool
```

如果 Meshy 分析不是 `healthy`，该命令会在提交 Meshy 多色付费请求前停止。审阅同一 session 的报告后，恢复而不是重跑 GPT Image 或 Hunyuan：

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_full_paid_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --session-id <existing-session-id> `
  --confirm-paid `
  --acknowledge-print-issues `
  --seed-calibration-spool
```

## 11. 健康检查与排障

```text
GET /health                      进程存活
GET /api/v1/creator/config       Creator 配置；返回明文，响应 no-store
```

常用命令：

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check backend\app backend\tests
npm --prefix .\frontend run lint
npm --prefix .\frontend run test:run
npm --prefix .\frontend run build
```

## 12. 相关文档

- [中文 README](README.md)
- [English README](README.en.md)
- [中文架构说明](BCA_ARCHITECTURE.zh-CN.md)
- [English architecture](BCA_ARCHITECTURE.md)
- [中文 Agent 开发契约](AGENTS.zh-CN.md)
- [文档审计](DOCUMENTATION_AUDIT.md)
