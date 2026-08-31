# BCA Agent 开发与工程契约

[English](AGENTS.md) | **中文**

本文件是 `bambuddy-create-agent` 的中文工程契约。英文 `AGENTS.md` 与本文件表达同一 BCA 实现边界；发生冲突时应先修正文档，不能让两套约束长期分歧。

## 1. 产品边界

BCA 是以 Bambuddy 为中心的自托管 3D 创作和打印管理后端：

```text
创意对话 / 可选参考图
  → brief 补全与追问
  → 明确确认图像生成
  → 四张串行概念图
  → 持久化选择
  → 明确确认 3D
  → 持久化 GLB
  → Meshy 多色模型 3MF
  → 几何白模 或 Bambuddy 耗材多色校准
  → BCA task
  → root 上传 .gcode.3mf
  → Bambuddy LibraryFile / PrintQueueItem
  → FTPS + MQTT project_file
```

Bambuddy 是打印机发现、打印机状态和别名、AMS、队列匹配、Library、切片、FTPS、MQTT、认证、用户、API Key、WebSocket、相机、Webhook 和部署的权威实现。BCA 不得创建第二套打印机状态机、队列、认证、文件存储、静态应用或独立 FastAPI 服务。

## 2. Provider 配置与付费调用

- Provider 凭据可以按产品决定在 Agent Services 中以明文填写、读取、返回与热加载。
- 明文值存为 Bambuddy settings 表中的 `bca_creator_*`；数据库读取者、数据库备份持有者及具备 `SETTINGS_READ` 的 API/网页调用者可以读取它们。
- `/api/v1/creator/config` 保留 Bambuddy 权限：GET 需要 `SETTINGS_READ`，PUT 需要 `SETTINGS_UPDATE`；不得创建无认证凭据接口。
- 配置响应必须使用：

```text
Cache-Control: private, no-store
```

- 不得将凭据写入普通 creator 会话、task、Provider 错误、普通日志、源码或公开文档。
- 对话或 issue 中给出的凭据一律视为已暴露，生产前应轮换。
- 图像、3D 和 Meshy 多色 Provider 的付费 POST 不得自动重试。
- 常规测试不得调用付费 Provider；只有明确批准后才使用 smoke runner 的 `--confirm-paid`。

## 3. 运行与部署

- Python 3.11+；本地使用仓库 `.venv`。
- React + Vite 构建到 `static/`，同一 FastAPI origin 提供 SPA 与 `/api/v1`。
- 当前 BCA 使用进程内锁和 task map；禁止增加多 Uvicorn worker 或多个 BCA 副本。
- Linux 推荐 host networking；Windows Docker Desktop 必须使用 bridge override。
- BCA 不读取 source-project `.env` / `.env.local`；环境变量只提供初始值，网页可覆盖并持久化。

本地启动：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
npm --prefix .\frontend ci
npm --prefix .\frontend run build
$env:DATA_DIR = "$PWD\data"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Windows Docker Desktop：

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml build
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d
curl http://127.0.0.1:8012/health
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml down
```

只有明确可丢弃的 smoke 测试栈才能使用 `down -v`；它会删除命名数据卷。

`network_mode: !reset null` 是 bridge override 的必要写法；不能替换为空字符串。

## 4. 后端结构

```text
backend/app/
├─ main.py                         FastAPI composition / lifespan
├─ api/routes/creator.py           /api/v1/creator
├─ api/routes/bca_tasks.py         /api/v1/bca-tasks
├─ services/creator_integration.py BCA 组合、配置、WS 事件
├─ services/creator_inventory.py   Bambuddy Spool → 颜色候选
├─ models/bca_task.py              BCA task 表
└─ three_d_agent/
   ├─ contracts.py                 公共模型、状态、Provider Protocol
   ├─ service.py                   状态机、确认门、持久化语义
   ├─ conversation.py              LangGraph 对话 planner
   ├─ graph.py                     免费 brief 图
   ├─ calibration.py               安全 3MF 转换
   ├─ storage.py                   session SQLite 与产物
   └─ providers/                   DeepSeek、Image、Hunyuan、Meshy
```

## 5. 创作状态机

```text
needs_input
  → awaiting_image_confirmation
  → queued_image → generating_images
  → awaiting_image_selection
  → awaiting_3d_confirmation
  → queued_3d → generating_3d
  → completed | failed
```

后置子流程：

```text
print_analysis:    not_started → queued → running → succeeded | failed
print_file:        not_started → queued → running → succeeded | failed
color_calibration: not_started → queued → running → succeeded | failed
geometry_status:   not_started → running → succeeded | failed
```

必须保持：

1. `prepare()` 免费，只负责 brief、追问和提示词。
2. 图像阶段要求完整 brief、`image_prompt` 和 `awaiting_image_confirmation`。
3. 图像严格四次串行 `n=1`；每张保存后立刻可见，必须四张后才能选择。
4. 3D 阶段要求已持久化的选择图和 `awaiting_3d_confirmation`。
5. BCA 不公开 Meshy repair。
6. 多色限制为 1–8；分析非 `healthy` 时必须显式确认问题。
7. 所有 Provider 结果在 API 暴露前必须下载、验证和持久化。
8. 取消/失败要持久化正确主状态或子状态。
9. 重做 `brief`、`images`、`model` 必须清除所有下游路径、状态、修复模型及跨模型待下载 Provider URL。

## 6. 对话 planner

`three_d_agent/conversation.py` 用 LangGraph `StateGraph` 选择单一安全动作：

```text
prepare | confirm_images | select_image | confirm_3d | analyze
| generate_print_file | geometry | calibrate | restart_question
```

LangGraph 只规划动作；`creator.py` 负责实际 service 调用。不要把付费 Provider 调用移动到图节点中。付费动作仍需要明确确认，且非健康分析的多色动作需要问题确认文本。

## 7. 产物与 3MF

模型 3MF 只证明存在：

```text
[Content_Types].xml
3D/*.model
```

它不是可直接打印的 job。切片上传必须包含：

```text
Metadata/plate_N.gcode
Metadata/slice_info.config
```

BCA 上传限制为 100 MB，并校验 ZIP 成员数量、成员大小、压缩比、解压总大小、重复成员和路径安全。几何和多色校准均是独立 3MF，不覆盖原始多色 3MF。

## 8. BCA Task

```text
awaiting_slice
  → attach validated .gcode.3mf → ready_for_queue
  → root chooses printer → queued
```

任务 API：

```text
GET    /api/v1/bca-tasks
POST   /api/v1/bca-tasks
GET    /api/v1/bca-tasks/{id}/source
POST   /api/v1/bca-tasks/{id}/sliced
POST   /api/v1/bca-tasks/{id}/queue
DELETE /api/v1/bca-tasks/{id}
```

队列交接调用原生 `add_to_queue()`，设置 `manual_start=True`。BCA 不复制原生队列逻辑。

## 9. 配置与外部接口

Creator 配置路由：

```text
GET /api/v1/creator/config     SETTINGS_READ
PUT /api/v1/creator/config     SETTINGS_UPDATE
```

持久化配置包括所有 Base URL/模型/运行参数及以下明文凭据：

```text
bca_creator_deepseek_api_key
bca_creator_image_api_key
bca_creator_tencent_secret_id
bca_creator_tencent_secret_key
bca_creator_meshy_api_key
```

启动时从数据库恢复，然后构建 `AgentSettings`、Provider 与 planner。Provider Base URL 必须通过 LAN-service URL 验证；不安全值返回 422。

## 10. WebSocket

Creator 后台阶段发布：

```json
{
  "type": "bca_creator_session",
  "session_id": "...",
  "stage": "images|model|analysis|print-file|geometry|calibration",
  "event": "running|updated|failed",
  "status": "..."
}
```

WebSocket 不是状态权威；SQLite snapshot 仍是权威，前端轮询可恢复失去的事件。

## 11. 数据库与迁移

- `init_db()` 导入 `bca_task`，新库由 `Base.metadata.create_all()` 创建 BCA table。
- `run_migrations()` 必须保持对旧 `bca_tasks.print_queue_item_id` 和索引的幂等升级。
- 为新持久化字段定义 SQLite/ PostgreSQL 迁移和旧数据默认值。
- PostgreSQL 部署要将 `DATABASE_URL` 的数据库 dump 与 `DATA_DIR` 一起备份与恢复；`bca_tasks`、`bca_creator_*` 在原生数据库，BCA 产物在 `DATA_DIR`。

## 12. 前端

```text
/creator            CreatorPage
/tasks              TaskListPage
/creator/settings   CreatorSettingsPage
```

Creator 页面为三列工作区：会话列表、对话/追问、工作流画布。效果图预览必须使用带认证的 Blob fetch，effect 清理中必须 abort 请求并 revoke 所有 object URL。`action()` 默认发送 POST，避免卡片操作变成 GET/405。

## 13. 验证

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check backend\app backend\tests
npm --prefix .\frontend run lint
npm --prefix .\frontend run test:run
npm --prefix .\frontend run build
```

非计费 Provider 配置检查：

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_provider_smoke.py --base-url http://127.0.0.1:8000
```

付费 smoke 只在明确批准后运行。若分析非 `healthy`，恢复同一 session，不能重新跑图像或 3D。

## 14. 开发完成检查

- 所有 route、状态、前端和测试同步更新。
- 明文配置 API 保留 `SETTINGS_READ/UPDATE` 权限和 `private, no-store` 响应。
- 没有未批准的付费调用。
- 模型 3MF 从未绕过验证直接排队。
- 产物仍只通过受控 BCA route 下载。
- 原生 Bambuddy queue/mapping 未被复制或绕过。
- 新持久化状态有迁移和备份策略。
- Docker 变化在 Docker 主机验证。

## 相关文档

- [中文 README](README.md)
- [English README](README.en.md)
- [中文部署指南](DEPLOYMENT_BCA.zh-CN.md)
- [English deployment guide](DEPLOYMENT_BCA.md)
- [中文架构说明](BCA_ARCHITECTURE.zh-CN.md)
