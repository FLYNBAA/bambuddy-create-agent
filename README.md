# Bambuddy Create Agent（BCA）

[English](README.en.md) | **中文**

BCA 是基于 Bambuddy 的二次开发：它将 AI 3D 创作、模型校准、任务交接嵌入 Bambuddy 的打印机、耗材、队列、权限和部署体系。它不是独立 create-agent 服务。

## 适用场景

- 在本地 Windows、局域网 Linux 或公网 Linux 服务器上运行自托管创作与打印后台。
- 通过对话或工作流卡片生成适合 3D 打印的模型。
- 使用 Bambuddy 原生打印机管理、打印队列、耗材库、API Key、Webhook、相机和权限。
- 让 root 在模型完成后上传切片结果，再安全派发到指定打印机。

## 工作流

```text
创意文字 / 可选参考图
  → DeepSeek 补全主体、风格、作品类型并追问缺项
  → 明确确认生成四张效果图
  → GPT Image 串行生成并逐张持久化候选图
  → 选择候选图并明确确认 3D
  → 腾讯混元生成并持久化 GLB
  → Meshy 免费打印分析
  → 明确确认多色模型 3MF（1–8 色槽）
  → 几何白模 或 Bambuddy 耗材库多色校准
  → BCA 任务清单
  → root 上传切片后的 .gcode.3mf
  → Bambuddy LibraryFile / PrintQueueItem
  → 原生 FTPS + MQTT 派发
```

## 重要约束

1. 图像、3D 和 Meshy 多色请求都有独立确认门；付费 POST 不会自动重试。
2. 效果图严格使用四次串行 `n=1` 请求；每张持久化后立即可见。
3. Meshy 拓扑修复没有暴露在 BCA UI 或 API 中。
4. 若分析状态不是 `healthy`，继续多色生成前必须单独确认已了解问题。
5. 重新开始创意、效果图或 3D 阶段时，旧模型的下游产物和挂起供应商 URL 会全部失效，不能再下载或交接。
6. 几何白模和多色校准 3MF 是独立产物；原始多色 3MF 保留。
7. BCA 模型 3MF 不能直接推送打印机。只有 root 上传并通过验证的切片 `.gcode.3mf` 才可进入原生队列。

有效切片包必须包含：

```text
Metadata/plate_N.gcode
Metadata/slice_info.config
```

## 后台页面

| 页面 | 路由 | 用途 |
|---|---|---|
| 3D Creator | `/creator` | 会话列表、Agent 对话、四阶段画布、候选选择、产物下载、校准和任务交接。 |
| BCA Tasks | `/tasks` | 下载模型、上传切片文件、选择 `命名（型号）` 打印机、提交原生队列、永久删除。 |
| Agent Services | `/creator/settings` | 热更新非密钥 Provider 地址和模型名；仅显示密钥是否已配置。 |
| 原生 Bambuddy 页面 | 打印机、耗材、队列等 | 保持 Bambuddy 原生行为和权限模型。 |

认证开启时，效果图预览通过带 Bearer token 的 Blob 请求加载；不要将受控效果图路由直接放到 `<img src>`。

## 本地开发（Windows）

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
npm --prefix .\frontend ci
npm --prefix .\frontend run build
$env:DATA_DIR = "$PWD\data"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000`。首次使用请按你的安全策略创建本地管理员并配置认证。

## 配置与密钥

- 参照 [`.env.bca.example`](.env.bca.example) 的**变量名**将 Provider 密钥注入部署环境、Docker Secret、Kubernetes Secret 或其他秘密管理器。
- BCA 不会读取 source-project 的 `.env` 或 `.env.local`。
- 不要在浏览器、数据库设置、任务记录、文档或源码中保存真实 Provider 密钥。
- Agent Services 页面仅允许修改非密钥设置；非法 Provider 基础 URL 返回 HTTP `422`。

需要的密钥变量：

```text
DEEPSEEK_API_KEY
IMAGE_API_KEY
TENCENT_SECRET_ID
TENCENT_SECRET_KEY
MESHY_API_KEY
```

当 `MESHY_MODEL_INPUT_MODE=public_url` 时，`BCA_PUBLIC_BASE_URL` 必须是可从公网访问的 HTTPS 地址。Meshy 只会得到受控的 GLB 能力路由：

```text
/api/v1/creator/sessions/{session_id}/model.glb
```

## Docker 与网络

Linux 推荐：

```bash
docker compose up -d --build
```

Windows Docker Desktop：

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d --build
curl http://127.0.0.1:8012/health
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml down -v
```

Linux 默认使用 host networking，以支持发现、Virtual Printer、相机与打印机 LAN 协议。Windows bridge override 使用 `network_mode: !reset null`，请使用打印机 LAN IP，并为 SSDP 或完整被动 FTP 范围额外映射端口。

## 备份与恢复

必须将下列内容作为**同一恢复点**备份和恢复：

1. `DATA_DIR`：包含 `bca-agent` 会话和产物、`bca-tasks` 源文件、归档和 Library 数据。
2. Bambuddy 原生数据库：SQLite 数据文件，或外部 PostgreSQL 的完整 dump。
3. 部署密钥配置：Secret manager、Docker Secret 或部署环境声明。

如果 `DATABASE_URL` 指向 PostgreSQL，仅备份 `DATA_DIR` 不足以恢复 BCA：`bca_tasks` 和持久化的 `bca_creator_*` 服务配置位于 Bambuddy 原生数据库。恢复时必须同时恢复数据库与对应 `DATA_DIR` 快照，避免任务行、LibraryFile、队列行与 BCA 产物脱节。

## 付费 smoke 策略

常规测试不得调用付费 Provider。仅在明确批准具体费用后使用：

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_full_paid_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --confirm-paid `
  --seed-calibration-spool
```

如果分析不是 `healthy`，初次链路会在 Meshy 前停止。审阅报告后，必须恢复同一会话，不能重新生成图像或 3D：

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_full_paid_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --session-id <existing-session-id> `
  --confirm-paid `
  --acknowledge-print-issues `
  --seed-calibration-spool
```

## 开发验证

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check backend\app backend\tests
npm --prefix .\frontend run lint
npm --prefix .\frontend run test:run
npm --prefix .\frontend run build
```

## 当前边界

当前 BCA 是单进程模型。会话锁、后台任务和任务调度不能通过增加 Uvicorn worker 扩展为多进程。多用户所有权隔离、分布式锁、持久队列恢复、对象存储和可验证 Provider webhook 是后续明确实现的能力，而非当前承诺。

## 相关文档

- [English README](README.en.md)
- [架构说明](BCA_ARCHITECTURE.md)
- [部署说明](DEPLOYMENT_BCA.md)
- [工程契约](AGENTS.md)
- [文档审计](DOCUMENTATION_AUDIT.md)
- [前端说明](frontend/README.md)
