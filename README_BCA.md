# BCA / Bambuddy Create Agent

> 中文在前，English follows each section. This document is the public BCA integration guide. `AGENTS.md` is the engineering contract; `BCA_ARCHITECTURE.md` and `DEPLOYMENT_BCA.md` are the detailed architecture and deployment references.

## 1. 项目定位 / What this is

**中文**：BCA 是嵌入 Bambuddy 的自托管 3D 创作与打印管理后端。Bambuddy 仍然是打印机、原生队列、Library、用户、权限、API Key、WebSocket 和部署的唯一权威；BCA 只拥有创作会话和创作产物。

**English**: BCA is a self-hosted 3D-creation and print-management backend embedded in Bambuddy. Bambuddy remains the sole authority for printers, native queueing, Library files, users, permissions, API keys, WebSockets, and deployment. BCA owns only creator sessions and their artifacts.

```text
创意对话 / 可选参考图
  → 创意补全与追问
  → 明确确认生成四张效果图
  → 逐张持久化候选图并选择
  → 明确确认生成 3D
  → 持久化 GLB
  → Meshy 分析与多色模型 3MF
  → 几何白模 或 耗材库多色校准
  → BCA 任务清单
  → root 上传切片后的 .gcode.3mf
  → Bambuddy LibraryFile / PrintQueueItem
  → 原生 FTPS + MQTT 打印派发
```

```text
Creative conversation / optional reference image
  → brief enrichment and clarification
  → explicit confirmation for four concept images
  → persist each candidate and select one
  → explicit confirmation for 3D generation
  → persisted GLB
  → Meshy analysis and model 3MF
  → geometry-white or inventory color calibration
  → BCA task list
  → root uploads sliced .gcode.3mf
  → Bambuddy LibraryFile / PrintQueueItem
  → native FTPS + MQTT dispatch
```

## 2. 核心约束 / Core constraints

| 中文 | English |
|---|---|
| 图像、3D、Meshy 多色生成均有明确付费确认门，绝不自动重试付费 POST。 | Image, 3D, and Meshy multi-color stages have explicit payment gates; billed POSTs are never auto-retried. |
| 效果图必须严格串行请求四次 `n=1`，每张保存后立即可见。 | Four images are requested serially as `n=1`; every persisted image becomes visible immediately. |
| Meshy 拓扑修复不在 BCA UI/API 中暴露。 | Meshy topology repair is intentionally not exposed in the BCA UI/API. |
| BCA 多色输出最多 8 色槽。 | BCA limits multi-color output to at most 8 color slots. |
| 分析不是 `healthy` 时，生成多色 3MF 前必须单独确认已了解问题。 | When analysis is not `healthy`, a separate acknowledgement of the reported issues is required before multi-color generation. |
| 重做创意、效果图或 3D 时会失效所有下游产物和挂起的供应商 URL，旧产物不能下载或交接。 | Restarting the brief, images, or model invalidates all downstream artifacts and pending provider URLs; stale output cannot be downloaded or handed off. |
| 只有几何白模或多色校准完成后的 3MF 才能加入任务清单。 | Only completed geometry or calibrated multi-color 3MFs can enter the task list. |
| 模型 3MF 不能直接打印；必须上传并验证切片后的 `.gcode.3mf`。 | A model 3MF is never directly printable; root must upload and validate a sliced `.gcode.3mf`. |

A valid sliced file must contain both:

```text
Metadata/plate_N.gcode
Metadata/slice_info.config
```

## 3. 后台界面 / Administration UI

**中文**：

- **3D Creator**：左侧会话列表、中间 Agent 对话和候选选项、右侧四阶段工作流画布。可直接点卡片，也可由对话规划操作。
- **BCA Tasks**：按创建时间倒序显示。root 可下载模型、上传切片文件、选择 `命名（型号）` 打印机并交给原生队列；可永久删除任务。
- **Agent Services**：热修改非密钥 Provider 地址和模型名；密钥仅显示“已配置/未配置”。
- **Filament / Printers / Print Queue**：沿用 Bambuddy 原生页面和权限模型。

**English**:

- **3D Creator**: session list on the left, Agent chat and choices in the center, and a four-stage workflow canvas on the right. Operators may use cards directly or let chat plan an action.
- **BCA Tasks**: newest first. Root can download a model, attach a sliced file, select a `name (model)` printer, hand off to the native queue, or permanently delete a task.
- **Agent Services**: hot-reloads non-secret provider URLs and model names; secrets are represented only as configured/unconfigured.
- **Filament / Printers / Print Queue**: retain native Bambuddy pages and permission semantics.

## 4. 安装与本地运行 / Install and local run

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
npm --prefix .\frontend ci
npm --prefix .\frontend run build
$env:DATA_DIR = "$PWD\data"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

**中文**：打开 `http://127.0.0.1:8000`。首次设置中创建本地管理员或按你的安全策略启用认证。Windows 本地可运行；生产 Linux 推荐 Docker 与 host networking。

**English**: Open `http://127.0.0.1:8000`. Create the initial local administrator or enable authentication according to your security policy. Windows local development is supported; production Linux deployments should use Docker and host networking.

## 5. 配置与密钥 / Configuration and secrets

**中文**：复制 `.env.bca.example` 的**字段名**到部署环境、Docker Secret、Kubernetes Secret 或其他秘密管理器。不要复制、读取或提交填充后的 `.env` 文件。BCA 不会自动读取 source-project `.env` 或 `.env.local`。

**English**: Copy only the **variable names** from `.env.bca.example` into the deployment environment, Docker/Kubernetes Secrets, or another secret manager. Never copy, read, or commit a populated `.env` file. BCA does not automatically read source-project `.env` or `.env.local` files.

Required provider secret variables:

```text
DEEPSEEK_API_KEY
IMAGE_API_KEY
TENCENT_SECRET_ID
TENCENT_SECRET_KEY
MESHY_API_KEY
```

Useful non-secret variables:

```text
BCA_PUBLIC_BASE_URL=https://bca.example.invalid
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
IMAGE_BASE_URL=https://api.example.invalid/v1
IMAGE_MODEL=gpt-image-2
IMAGE_QUALITY=high
MESHY_MODEL_INPUT_MODE=data_uri
```

When `MESHY_MODEL_INPUT_MODE=public_url`, `BCA_PUBLIC_BASE_URL` must be a publicly reachable HTTPS origin. Meshy receives only the controlled provider capability route:

```text
/api/v1/creator/sessions/{session_id}/model.glb
```

## 6. Docker 与网络 / Docker and networking

**Linux / Linux**:

```bash
docker compose up -d --build
```

**Windows Docker Desktop / Windows Docker Desktop**:

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d --build
curl http://127.0.0.1:8012/health
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml down -v
```

**中文**：Linux 默认使用 host networking，以支持发现、Virtual Printer、相机和 LAN 打印机协议。Windows bridge override 使用 `network_mode: !reset null`，需要手工以 LAN IP 添加打印机；SSDP 与完整被动 FTP 端口范围需要额外映射。

**English**: Linux defaults to host networking for discovery, Virtual Printer, cameras, and LAN printer protocols. The Windows bridge override uses `network_mode: !reset null`; add printers by LAN IP, and map extra ports for SSDP or the full passive FTP range.

## 7. 付费 smoke / Paid smoke policy

**中文**：常规测试不得调用付费 Provider。只有在人工批准具体费用后运行 `backend/tools/bca_full_paid_smoke.py --confirm-paid`。如果打印分析不是 `healthy`，初次链路会停在 Meshy 前；审阅报告后，必须以相同会话的 `--session-id` 和 `--acknowledge-print-issues` 恢复，不能重新跑图像或混元阶段。

**English**: Routine tests must never invoke billed providers. Run `backend/tools/bca_full_paid_smoke.py --confirm-paid` only after approving the exact charges. If print analysis is not `healthy`, the initial chain stops before Meshy. Review the report, then resume the same session with `--session-id` and `--acknowledge-print-issues`; never repeat the image or Hunyuan stages.

See `DEPLOYMENT_BCA.md` for the exact commands.

## 8. API 摘要 / API summary

| Group | Routes |
|---|---|
| Creator | `/api/v1/creator/sessions`, `prepare`, `chat`, `confirm-image`, `select-image`, `confirm-3d`, `print/analyze`, `print/generate`, `print/geometry`, `print/calibrate`, `task` |
| Creator artifacts | controlled image, GLB, original 3MF, geometry 3MF, and calibrated 3MF downloads |
| Tasks | `/api/v1/bca-tasks`, `/{id}/source`, `/{id}/sliced`, `/{id}/queue` |
| Native integration | Bambuddy printer, queue, inventory, camera, API-key and webhook APIs |

**中文**：所有普通 BCA 路由使用 Bambuddy 权限依赖；不返回服务器绝对路径、供应商签名 URL、任务 ID 或密钥。

**English**: Ordinary BCA routes use Bambuddy permission dependencies and never return server absolute paths, provider signed URLs, provider job IDs, or secrets.

## 9. 验证 / Verification

```powershell
$env:PYTHONPATH = "."
\.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check backend\app backend\tests
npm --prefix .\frontend run lint
npm --prefix .\frontend run build
```

For BCA-focused checks, see `AGENTS.md`.

## 10. 长期边界 / Long-term boundaries

**中文**：当前任务、会话锁和后台任务是单进程模型。多用户隔离、分布式锁、持久队列恢复、对象存储与 Provider webhook 验证属于未来扩展；不要通过增加 Uvicorn workers 伪装已支持它们。

**English**: Current tasks, session locks, and background work are single-process. Multi-user isolation, distributed locking, durable queue recovery, object storage, and verified provider webhooks are future extensions; do not pretend they are supported by merely adding Uvicorn workers.

---

- Engineering contract: [`AGENTS.md`](AGENTS.md)
- Architecture: [`BCA_ARCHITECTURE.md`](BCA_ARCHITECTURE.md)
- Deployment: [`DEPLOYMENT_BCA.md`](DEPLOYMENT_BCA.md)
- Secret template: [`.env.bca.example`](.env.bca.example)
- Upstream Bambuddy documentation: [`README.md`](README.md)
