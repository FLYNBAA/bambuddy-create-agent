# BCA 架构说明

[English](BCA_ARCHITECTURE.md) | **中文**

## 范围与职责

BCA 是嵌入 Bambuddy 的单进程 3D 创作与打印管理模块。Bambuddy 是打印机、原生队列、Library、认证、用户、API Key、WebSocket 与部署的唯一权威；BCA 只管理创作会话和创作产物。

```text
Creator 会话
  → 持久化 GLB
  → Meshy 模型 3MF
  → 几何白模 或 耗材校准 3MF
  → BCA 任务清单
  → root 上传 .gcode.3mf
  → Bambuddy LibraryFile
  → Bambuddy PrintQueueItem
  → 原生 FTPS + MQTT project_file
```

BCA 产物绝不直接进打印机。root 上传的切片文件必须包含：

```text
Metadata/plate_N.gcode
Metadata/slice_info.config
```

## 模块边界

| 模块 | 职责 |
|---|---|
| `backend/app/three_d_agent/` | 创作状态机、Provider Protocol、产物验证、颜色与几何转换。 |
| `backend/app/services/creator_integration.py` | BCA/Bambuddy 组合边界、配置持久化、后台阶段与 WebSocket 事件。 |
| `backend/app/api/routes/creator.py` | `/api/v1/creator` 的会话、配置、付费门与受控下载。 |
| `backend/app/models/bca_task.py` | BCA 任务持久化模型。 |
| `backend/app/api/routes/bca_tasks.py` | 模型上传、切片验证和明确队列交接。 |
| `library.py`、`print_queue.py`、`print_scheduler.py` | Bambuddy 原生 Library、队列、映射和运输权威实现。 |

## 创作不变量

1. 图像和 3D Provider 只能在明确确认后调用。
2. 四张概念图使用四个串行的付费 `n=1` 请求，不做付费自动重试。
3. 每张图返回后立即持久化与展示；认证打开时前端通过带 Bearer token 的 Blob URL 预览，不直接把受控路由赋给 `<img>`。
4. BCA 不暴露 Meshy topology repair。
5. 多色转换只允许 1–8 个颜色槽；分析不是 `healthy` 时，多色请求前必须显式确认已了解问题。
6. 几何模式将可支持颜色元数据归一为白色，保留面/属性引用和几何。取消或进程重启恢复后状态必须是 `failed`，不能永久停在 `running`。
7. 多色校准从活动、未归档的 Bambuddy 手动耗材读取有效 RGB；没有候选耗材时失败，不使用本地近似色回退。
8. 只有成功的几何白模或多色校准 3MF 能创建 `BCATask`。
9. 重做 `brief`、`images` 或 `model` 时，必须清空下游路径、状态、修复 GLB、待下载 Meshy repair/print URL。仅重做同一模型的 `print` 时保留待下载 URL。
10. 删除 creator 会话只删除 BCA 自有文件；删除 BCA 任务不会删除已创建的 LibraryFile 或原生队列项。

## 任务状态机

```text
awaiting_slice
  → root 上传通过验证的 .gcode.3mf → ready_for_queue
  → root 选择 printer_id → queued
```

交接通过原生 `add_to_queue()` 创建 `manual_start=True` 的 `PrintQueueItem`。后续开始、取消、AMS、材料匹配、FTPS、MQTT、打印状态和归档全部仍由 Bambuddy 处理。

## HTTP 边界

- `/api/v1/creator/*`：creator 会话、聊天、确认门、分析/校准、受控产物下载和任务交接。
- `/api/v1/bca-tasks/*`：任务列表、源文件下载、切片附加、队列提交和永久删除。
- 正常 creator/BCA 路由使用 Bambuddy 权限依赖；不得暴露服务器绝对路径、Provider 临时 URL 或 Provider job ID。
- Meshy `public_url` 输入仅使用高熵能力路由：

```text
GET /api/v1/creator/sessions/{session_id}/model.glb
```

该路由不出现在普通会话快照中；普通产物下载仍需要权限。

## 明文 Provider 配置

环境变量提供初始值，Agent Services 可以运行时替换所有 Provider 参数和明文凭据。BCA 不读取 source-project `.env` / `.env.local`。

所有 Creator 配置均保存在 Bambuddy settings 表的 `bca_creator_*` 行，并在 FastAPI lifespan 启动时恢复：

```text
bca_creator_deepseek_api_key
bca_creator_image_api_key
bca_creator_tencent_secret_id
bca_creator_tencent_secret_key
bca_creator_meshy_api_key
```

及对应 Base URL、模型、质量、地区、Meshy 输入模式和公开地址字段。`GET /api/v1/creator/config` 会向 `SETTINGS_READ` 调用方返回明文值；`PUT` 需要 `SETTINGS_UPDATE` 并会重新创建 `AgentSettings`、Provider 和 LangGraph planner。配置响应总是：

```text
Cache-Control: private, no-store
```

Provider Base URL 仍需经过 LAN-service HTTP(S) URL 验证；不安全值返回 HTTP `422`。

## 部署模型

同一个 Bambuddy Dockerfile 构建 React 到 `/static` 并运行一个 FastAPI 进程。BCA 依赖在 `requirements.txt`；产物在：

```text
DATA_DIR/bca-agent/   会话、概念图、GLB、3MF
DATA_DIR/bca-tasks/   等待切片的任务源文件
```

`BCA_PUBLIC_BASE_URL` 只在 `MESHY_MODEL_INPUT_MODE=public_url` 时需要，必须是 Meshy 可访问的 HTTPS 公开地址。

当前锁和后台任务均为单进程内存模型。不要通过增加 Uvicorn workers 或 BCA 副本来伪装支持多进程。分布式锁、持久 Worker 恢复、对象存储、多用户所有权隔离、可验证 webhook 均是未来工作。

## 相关文档

- [中文 README](README.md)
- [English README](README.en.md)
- [中文部署指南](DEPLOYMENT_BCA.zh-CN.md)
- [工程契约中文说明](AGENTS.zh-CN.md)
