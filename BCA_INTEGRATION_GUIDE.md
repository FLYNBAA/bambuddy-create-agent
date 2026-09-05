# Bambuddy / BCA 接口对接说明

> 范围：BCA 全部对接接口 + 常用原生 Bambuddy 接口
>
> 本文面向第三方系统、自动化脚本和前端客户端。BCA 接口、任务交接、WebSocket 和常用原生接口在文中给出字段与行为说明；原生 Bambuddy 的大量管理/设备路由未在本文逐一展开，完整的 path、method、参数、请求体、响应 schema 和 OpenAPI security 以目标运行实例的 `{ORIGIN}/openapi.json` 为准。Swagger UI 位于 `{ORIGIN}/docs`。
>
> 契约核验基线：当前源码路由实现 + 运行实例 OpenAPI 3.1.0（当前应用版本由实例返回）。本文不固化运行容器抓取的 OpenAPI JSON 快照；部署后请重新读取目标实例的 `/openapi.json`。

## 1. 产品边界

BCA 是 Bambuddy 进程内的创作工作流，不是第二个独立服务。Bambuddy 继续负责：

- 用户、JWT、API Key、权限和 WebSocket 认证；
- 打印机发现、连接、状态、别名、AMS、耗材和队列；
- Library 文件、切片、FTPS、MQTT、打印生命周期；
- 相机、Webhook、备份、静态 SPA 和部署。

BCA 只负责创作会话、创作产物、颜色校准和订单任务。不要为 BCA 另建认证、文件存储、打印机状态机或队列。

## 2. 服务地址与部署

### 2.1 Base URL

所有 HTTP API 使用同源前缀：

```text
{ORIGIN}/api/v1
```

例如：

```text
http://127.0.0.1:8000/api/v1
https://bca.example.com/api/v1
```

健康检查不在 `/api/v1` 下：

```text
GET {ORIGIN}/health
```

### 2.2 Linux

Linux 默认使用 host network：

```bash
docker compose --env-file .env.bca up -d --build
curl http://127.0.0.1:8000/health
```

### 2.3 Windows Docker Desktop / Bridge

Windows 必须叠加 bridge override：

```powershell
docker compose --env-file .env.bca `
  -f .\docker-compose.yml `
  -f .\docker-compose.windows.yml `
  up -d --build

curl.exe http://127.0.0.1:8012/health
```

接口地址为：

```text
http://127.0.0.1:8012/api/v1
```

Bridge 模式不提供 Linux host network 的 SSDP 多播能力；打印机发现应配置 `BCA_DISCOVERY_SUBNETS`，或直接使用打印机 LAN IP。

### 2.4 反向代理

公网接入应使用 HTTPS 和同源反向代理。代理必须：

- 转发 `/api/v1` 和 SPA；
- 转发 `/api/v1/ws` 的 `Upgrade`、`Connection`；
- 对大型 3MF 上传设置至少 550 MB 的请求上限；
- 对 Meshy/Hunyuan 长请求关闭请求/响应缓冲，并允许最长约 1000 秒；
- WebSocket 允许长连接，建议读取超时 3600 秒。

仓库参考配置：[`deploy/nginx/bca.conf`](../deploy/nginx/bca.conf)。

## 3. 通用 HTTP 约定

### 3.1 请求头

JSON 请求：

```http
Content-Type: application/json
Accept: application/json
Authorization: Bearer <JWT-or-api-key>
```

文件上传使用 `multipart/form-data`。不要手工设置 multipart 的 `Content-Type`，让 HTTP 客户端生成 boundary：

```bash
curl -X POST "$BASE/api/v1/creator/sessions/$SESSION/prepare" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'message=一只适合打印的猫咪摆件' \
  -F 'reference_image=@reference.png;type=image/png'
```

API Key 可使用以下任一方式：

```http
X-API-Key: bb_<key>
```

或：

```http
Authorization: Bearer bb_<key>
```

JWT 和 API Key 不要放在 URL 查询参数中。相机流和 WebSocket 使用查询参数时，仅使用专门签发的短期 token。

### 3.2 成功响应

- `200 OK`：同步读取或更新成功；
- `201 Created`：创建资源成功；
- `202 Accepted`：后台阶段已排队，不能据此认为 Provider 已完成；
- `204 No Content`：删除成功，不应解析 JSON body；
- 文件接口返回二进制，并带 `Content-Type`、`Content-Disposition`。

### 3.3 错误响应

FastAPI 校验错误通常为：

```json
{
  "detail": [
    {
      "type": "string_too_long",
      "loc": ["body", "title"],
      "msg": "String should have at most 120 characters",
      "input": "..."
    }
  ]
}
```

业务错误通常为：

```json
{"detail": "human-readable message"}
```

部分原生接口返回结构化 detail：

```json
{"detail": {"code": "stable_code", "message": "human-readable message"}}
```

客户端必须同时兼容字符串、数组和对象三种 `detail`，并按 HTTP 状态码处理：

| 状态码 | 含义 | 对接处理 |
|---|---|---|
| 400 | 请求语义错误或当前配置不允许 | 修正请求或配置，不要盲目重试 |
| 401 | 缺少、无效、过期或已撤销凭据 | 重新登录或换有效 API Key |
| 403 | 用户/Key 没有所需权限或资源范围 | 不要重试；申请正确权限 |
| 404 | 资源或产物不存在 | 刷新资源状态；文件缺失时不要继续提交 |
| 409 | 状态冲突、并发操作或前置阶段未完成 | 读取最新状态后按状态机继续 |
| 413 | 上传超过限制 | 压缩或更换文件；不要重试同一文件 |
| 422 | 字段、文件格式或业务校验失败 | 修正字段/文件 |
| 429 | 容量或速率限制 | 尊重 `Retry-After`；校准忙时默认 120 秒 |
| 500 | 服务内部错误 | 记录 trace ID，检查服务日志 |
| 502 | Provider 调用失败 | 记录错误；付费 POST 不要自动重试 |
| 503 | Provider 未配置或服务不可用 | 检查配置和 Provider 状态 |

响应中的 `X-Trace-Id` 应被客户端记录，排查问题时提供该值，而不是提交凭据或完整请求体。

## 4. 认证初始化与登录

### 4.1 查询认证状态

```http
GET /api/v1/auth/status
```

响应：

```json
{
  "auth_enabled": true,
  "requires_setup": false
}
```

首次安装由管理员调用：

```http
POST /api/v1/auth/setup
Content-Type: application/json
```

请求体由 OpenAPI 的 `SetupRequest` 定义；启用认证且尚无管理员时，必须提供管理员用户名和符合复杂度要求的密码。认证已经配置后，不能用该接口匿名修改。

### 4.2 登录

```http
POST /api/v1/auth/login
Content-Type: application/json
```

```json
{
  "username": "admin",
  "password": "<password>"
}
```

无 2FA 时响应包含：

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "user": {"...": "UserResponse"},
  "requires_2fa": false,
  "pre_auth_token": null,
  "two_fa_methods": []
}
```

启用 2FA 时，响应不提供最终 JWT，而是返回：

```json
{
  "access_token": null,
  "requires_2fa": true,
  "pre_auth_token": "<short-lived-pre-auth-token>",
  "two_fa_methods": ["totp", "backup"]
}
```

随后按 `two_fa_methods` 调用 `/api/v1/auth/2fa/*`，成功后再取得最终访问 token。完整 TOTP、邮件 OTP、备份码和 OIDC 接口见 OpenAPI 的 `2fa` / `oidc` 标签。

### 4.3 当前用户与登出

```http
GET  /api/v1/auth/me
POST /api/v1/auth/logout
```

`/auth/me` 同时接受 JWT 和 API Key，并返回当前用户及该 API Key 实际可执行的权限范围。登出会撤销当前 JWT。

## 5. API Key 对接

API Key 管理接口：

```text
GET    /api/v1/api-keys/
POST   /api/v1/api-keys/
GET    /api/v1/api-keys/{key_id}
PATCH  /api/v1/api-keys/{key_id}
DELETE /api/v1/api-keys/{key_id}
```

创建示例：

```json
{
  "name": "automation",
  "can_read_status": true,
  "can_queue": true,
  "can_control_printer": false,
  "can_manage_library": true,
  "can_manage_inventory": false,
  "can_manage_maintenance": false,
  "can_manage_archives": false,
  "can_manage_projects": false,
  "can_access_cloud": false,
  "can_update_energy_cost": false,
  "printer_ids": [1],
  "expires_at": null
}
```

完整 Key 仅在 `POST /api-keys/` 的响应中返回一次：

```json
{
  "id": 1,
  "name": "automation",
  "key_prefix": "bb_...",
  "key": "bb_<full-secret-shown-once>",
  "enabled": true,
  "printer_ids": [1]
}
```

立即将 `key` 写入外部密钥管理器；之后只能读取前缀和元数据，不能恢复完整 Key。不要把 Key 写入 Git、日志、URL、任务备注或前端错误上报。

API Key scope 是权限上限，不会提升其创建者权限：

| Scope | 典型能力 |
|---|---|
| `can_read_status` | 状态、只读资源、历史、统计、WebSocket |
| `can_queue` | 创建/修改/删除队列、重打印、BCA 创作操作 |
| `can_control_printer` | 打印机控制、打印机文件、AMS 控制、智能插座控制 |
| `can_manage_library` | Library 上传/整理、MakerWorld 导入 |
| `can_manage_inventory` | 耗材、目录、预测和 SpoolBuddy 写入 |
| `can_manage_maintenance` | 维护项目与维护类型写入 |
| `can_manage_archives` | Archive 创建、整理和删除 |
| `can_manage_projects` | 项目写入 |
| `can_access_cloud` | Bambu/Orca Cloud 相关操作；需要有归属用户 |

未映射的管理类权限默认拒绝。尤其是设置、用户、组、API Key、备份恢复、Discovery 扫描和固件更新等，不会因为设置了某个普通 scope 而开放。

## 6. BCA 直接工作流接口（推荐）

直接工作流是：

```text
brief/prepare
  → image2/generate（可重复调用四次）
  → model/generate
  → print/multicolor 或 print/calibrate
  → print/analyze
  → task
  → BCA task sliced
  → native queue
```

所有直接模块接口都需要 `QUEUE_CREATE`。它们不创建浏览器会话；每次响应完成后会清理临时工作目录。除非明确说明，Provider 调用可能产生费用，生产客户端不得自动重试付费 POST。

### 6.1 准备创意 brief

```http
POST /api/v1/creator/modules/brief/prepare
Content-Type: application/json
```

```json
{
  "message": "做一个适合桌面摆件的太空猫，低多边形，底座稳定",
  "current_brief": {},
  "has_reference_image": false
}
```

字段：

- `message`：必填，1–4000 字符；
- `current_brief`：可选，已有 `CreativeBrief`，默认空对象；
- `has_reference_image`：是否有参考图，仅影响 brief/prompt 准备上下文。

响应：

```json
{
  "language": "zh",
  "brief": {},
  "questions": [],
  "image_prompt_ready": true,
  "prompts": {},
  "presentation": "..."
}
```

当前产品规则是完整输入自动准备；正常接受的输入返回空 `questions`，并将 `image_prompt_ready` 设为 `true`。客户端不要实现第二套澄清状态机。

### 6.2 生成一张 Image2 风格图

```http
POST /api/v1/creator/modules/image2/generate
Content-Type: multipart/form-data
```

字段：

- `prompt`：必填，1–8000 字符；
- `reference_image`：可选，最大 8 MiB（实际上限取 Creator 配置）。

响应为 `image/png` 文件 `style-image.png`，并带：

```http
X-BCA-Module: standalone
X-BCA-Image-Shape: 1:1
X-BCA-Image-Revised: true   # Provider 返回 revised prompt 时才有
```

### 6.3 从输入图生成 GLB

```http
POST /api/v1/creator/modules/model/generate
Content-Type: multipart/form-data
```

字段：

- `image`：必填，最大 8 MiB。

响应为 `model/gltf-binary` 文件 `model.glb`。客户端应检查响应状态和 `Content-Type` 后再保存文件。

### 6.4 生成多色 3MF

```http
POST /api/v1/creator/modules/print/multicolor
Content-Type: multipart/form-data
```

字段：

- `model`：无 `meshy_result_url` 时必填，必须是 GLB，最大 100 MiB；
- `max_colors`：必填，1–8；
- `meshy_result_url`：可选。传入此前已取得的 Meshy 结果 URL 时跳过新的 Meshy 提交，只下载和验证已有结果。

响应为 `model/3mf` 文件 `multicolor.3mf`，响应头：

```http
X-BCA-Module: standalone
X-BCA-Meshy-Reused: true|false
X-BCA-Color-Snapshot: created|present|skipped
```

GLB 必须是 glTF 2，且头部声明大小必须与实际上传字节数一致。结果 3MF 会尽力嵌入 `Metadata/plate_1.png` 彩色快照；快照缺失不会使有效 3MF 失败。

### 6.5 颜色校准

```http
POST /api/v1/creator/modules/print/calibrate
Content-Type: multipart/form-data
```

字段：

- `file`：必填，模型 3MF，最大 512 MiB。

接口只允许一个大包校准请求同时运行。忙时返回：

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 120
```

成功响应为 `model/3mf` 文件 `calibrated.3mf`，并带：

```http
X-BCA-Calibration-Colors: <mapping-count>
X-BCA-Calibration-Changes: <changed-count>
X-BCA-Color-Snapshot: replaced|skipped
```

校准只使用 Bambuddy 活跃耗材行：`archived_at IS NULL`、有非空 `material` 且颜色是有效 RGB/RGBA。没有可用库存时返回 422；不会虚构颜色或使用 `color_catalog` 作为校准库存。

### 6.6 打印分析

```http
POST /api/v1/creator/modules/print/analyze
Content-Type: multipart/form-data
```

字段：

- `model`：必填 GLB，最大 100 MiB，必须通过 GLB 头和大小校验。

响应：

```json
{
  "report": {},
  "assessment": {
    "score": 87,
    "insights": ["...", "..."]
  }
}
```

`score` 为 0–100，`insights` 为 1–8 条事实性洞察。该接口不输出打印建议。

### 6.7 直接模块错误映射

- Provider 未配置：503；
- Provider 调用失败：502；
- 文件/字段校验失败：422；
- 校准并发槽已占用：429；
- 未预期服务错误：500。

## 7. BCA 会话接口（兼容 Creator 页面）

会话接口适合 Creator 页面或需要持久化阶段状态的客户端；新公网集成优先使用第 6 节的无会话模块接口。

### 7.1 会话资源

```text
GET    /api/v1/creator/sessions
POST   /api/v1/creator/sessions
GET    /api/v1/creator/sessions/{session_id}
DELETE /api/v1/creator/sessions/{session_id}
```

`POST` 返回 `201` 并创建会话。`GET` 返回完整 `CreatorSessionResponse`：

```json
{
  "session_id": "...",
  "status": "...",
  "brief": {},
  "questions": [],
  "image_prompt": "...",
  "presentation_en": "...",
  "presentation_zh": "...",
  "generated_images": ["/api/v1/creator/sessions/<id>/images/0"],
  "image_generation": {"status": "not_started|queued|running|succeeded|failed"},
  "model_generation": {"status": "not_started|queued|running|succeeded|failed"},
  "selected_image_index": 0,
  "model_download_url": "/api/v1/creator/sessions/<id>/model",
  "calibrated_print_file_download_url": "/api/v1/creator/sessions/<id>/calibrated-print-file",
  "print_analysis": {},
  "color_calibration": {},
  "events": [],
  "error": null
}
```

客户端必须把持久化 snapshot 当作权威状态。`202` 只表示阶段已经排队。

### 7.2 阶段操作

```text
POST /api/v1/creator/sessions/{id}/prepare
POST /api/v1/creator/sessions/{id}/restart
POST /api/v1/creator/sessions/{id}/images/generate
POST /api/v1/creator/sessions/{id}/model/generate
POST /api/v1/creator/sessions/{id}/print/calibrate
POST /api/v1/creator/sessions/{id}/print/analyze
```

`prepare` 使用 multipart：

- `message`：表单字段，最大 4000；
- `reference_image`：可选，受 Creator `max_upload_bytes` 限制，默认 8 MiB。

`restart` JSON：

```json
{"stage":"brief"}
```

`stage` 只能是 `brief`、`images`、`model`、`print`。重做会清除该阶段及所有下游状态、文件、Provider URL 和任务资格。

`model/generate` JSON：

```json
{"image_index":0}
```

`print/calibrate` JSON：

```json
{"mode":"white","max_colors":8}
```

其中 `mode` 为 `white` 或 `multicolor`，`max_colors` 为 1–8。所有异步阶段返回 `202` 和最新 snapshot。

### 7.3 会话产物

```text
GET /api/v1/creator/sessions/{session_id}/images/{image_index}
GET /api/v1/creator/sessions/{session_id}/{artifact}
```

`artifact` 仅可取 `model` 或 `calibrated-print-file`。这些接口需要 `QUEUE_READ_ALL`，并只返回当前会话目录内已验证的文件。不存在、索引越界、未知 artifact 或阶段尚未成功时返回 404。


Provider 专用 capability-token URL 不在 OpenAPI schema 中，不是普通客户端接口；不要记录、公开或自行拼接。

### 7.4 会话配置

```text
GET /api/v1/creator/config
PUT /api/v1/creator/config
```

两者都需要 `SETTINGS_UPDATE`，响应均设置：

```http
Cache-Control: private, no-store
```

GET 只返回非秘密配置及布尔状态：

```json
{
  "deepseek_base_url": "...",
  "deepseek_model": "...",
  "image_base_url": "...",
  "image_model": "...",
  "image_quality": "...",
  "tencent_region": "...",
  "meshy_base_url": "...",
  "meshy_model_input_mode": "...",
  "app_public_base_url": "...",
  "configured": {
    "deepseek": true,
    "image": true,
    "hunyuan": true,
    "meshy": true
  }
}
```

PUT 接受同名配置字段。以下字段只写不回显：

```text
deepseek_api_key
image_api_key
tencent_secret_id
tencent_secret_key
meshy_api_key
```

配置接口可热加载，但已有 Creator Provider 操作运行时修改会返回 409。Provider base URL 会进行 LAN/URL 安全校验。真实凭据不得出现在文档、日志、源码、错误响应、任务快照或 Git。

## 8. BCA Task 与原生队列交接

BCA 任务状态：

```text
awaiting_slice
  → ready_for_queue
  → queued
```

切片失败或重新请求时也可接受 sliced 文件：`slice_requested`、`slice_failed`。

### 8.1 创建任务

有完整 Creator 会话时：

```http
POST /api/v1/creator/sessions/{session_id}/task
```

```json
{
  "title": "桌面太空猫",
  "customer_name": "张三",
  "phone": "13800000000",
  "address": "某市某路 1 号",
  "notes": "白色版本"
}
```

`customer_name`、`phone`、`address` 必填，分别最多 120、40、500 字符；`title` 最多 120，`notes` 最多 2000。创建前必须已经有：

- 最终校准 3MF；
- 已选择的风格图；
- GLB 模型；
- 成功的打印分析。

不满足时返回 409。成功返回 `201`：

```json
{"task_id": 123, "status": "awaiting_slice"}
```

### 8.2 直接上传模型任务

```http
POST /api/v1/bca-tasks
Content-Type: multipart/form-data
```

字段：

- `file`：必填模型 `.3mf`；
- `title`：可选，最多 120；
- `customer_name`：可选，最多 120；
- `phone`：可选，最多 40；
- `address`：可选，最多 500；
- `notes`：可选，最多 2000；
- `price`：可选，最多 64；
- `reference_image`：可选，最大 8 MiB。

直接上传只接受模型 `.3mf`：

- 拒绝 GLB；
- 拒绝切片 `.gcode.3mf`；
- 必须包含 `[Content_Types].xml` 和 `3D/*.model`；
- 文件包上限 512 MiB，并执行重复成员、压缩比、未压缩大小等安全校验。

成功返回 `201 BCATaskResponse`：

```json
{
  "id": 123,
  "session_id": null,
  "filename": "model.3mf",
  "status": "awaiting_slice",
  "sliced_library_file_id": null,
  "print_queue_item_id": null,
  "username": "root",
  "created_by": "root",
  "title": "model",
  "customer_name": "",
  "phone": "",
  "address": "",
  "notes": null,
  "price": null,
  "style_image_preview_url": null,
  "model_preview_url": null,
  "source_3mf_url": "/api/v1/bca-tasks/123/source",
  "source_3mf_snapshot_url": "/api/v1/bca-tasks/123/snapshot",
  "created_at": "<ISO-8601>",
  "updated_at": "<ISO-8601>"
}
```

### 8.3 查询与下载

```text
GET /api/v1/bca-tasks
GET /api/v1/bca-tasks/{id}/source
GET /api/v1/bca-tasks/{id}/snapshot
GET /api/v1/bca-tasks/{id}/style-image
GET /api/v1/bca-tasks/{id}/model-preview
```

任务列表按创建时间倒序。`source` 返回完整模型 3MF；`snapshot` 只返回内嵌的 `Metadata/plate_1.png`，不会渲染或返回完整 3MF 几何。没有快照返回 404。style image 为 PNG，model preview 为 GLB；不存在时返回 404。

### 8.4 附加 root 切片文件

```http
POST /api/v1/bca-tasks/{id}/sliced
Content-Type: multipart/form-data
```

字段：`file`，文件名必须以 `.gcode.3mf` 结尾，最大 512 MiB，并且必须包含：

```text
Metadata/plate_N.gcode
Metadata/slice_info.config
```

只有验证通过的 sliced 3MF 才会写入 Bambuddy Library，任务状态改为 `ready_for_queue`。模型 3MF 不得直接进入原生打印队列。

### 8.5 加入原生队列

```http
POST /api/v1/bca-tasks/{id}/queue
Content-Type: application/json
```

```json
{
  "printer_id": 1,
  "plate_id": 1
}
```

`printer_id` 必填且大于 0；`plate_id` 可空或大于等于 1。任务必须是 `ready_for_queue` 且已绑定 sliced Library 文件，否则返回 409。

成功后调用 Bambuddy 原生 `add_to_queue()`，使用 `manual_start=true`，任务状态为 `queued`。后续 AMS、材料匹配、FTPS、MQTT、开始/暂停/停止和打印状态全部由原生 Bambuddy 负责。

### 8.6 删除任务

```http
DELETE /api/v1/bca-tasks/{id}
```

需要 `QUEUE_DELETE_ALL`，成功返回 204。只删除 BCA 任务和 BCA 自有源文件，不删除已经创建的原生 LibraryFile 或 PrintQueueItem。

## 9. 原生 Bambuddy 对接接口

以下接口是打印管理集成最常用的原生表面；每个资源的完整字段、查询参数和权限以 `/openapi.json` 为准。

### 9.1 打印机

```text
GET    /api/v1/printers/
POST   /api/v1/printers/
GET    /api/v1/printers/{printer_id}
PATCH  /api/v1/printers/{printer_id}
DELETE /api/v1/printers/{printer_id}
GET    /api/v1/printers/{printer_id}/status
POST   /api/v1/printers/{printer_id}/connect
POST   /api/v1/printers/{printer_id}/disconnect
POST   /api/v1/printers/{printer_id}/refresh-status
GET    /api/v1/printers/{printer_id}/diagnostic
POST   /api/v1/printers/diagnostic
```

打印机控制包括：

```text
POST /api/v1/printers/{printer_id}/print/stop
POST /api/v1/printers/{printer_id}/print/pause
POST /api/v1/printers/{printer_id}/print/resume
POST /api/v1/printers/{printer_id}/clear-plate
POST /api/v1/printers/{printer_id}/temperature/nozzle
POST /api/v1/printers/{printer_id}/temperature/bed
POST /api/v1/printers/{printer_id}/temperature/chamber
POST /api/v1/printers/{printer_id}/fan-speed
POST /api/v1/printers/{printer_id}/print-speed
POST /api/v1/printers/{printer_id}/ams/load
POST /api/v1/printers/{printer_id}/ams/unload
```

开始打印应使用原生队列的 `POST /api/v1/queue/{item_id}/start`；不要绕过队列直接向打印机发送 BCA 文件。


### 9.2 原生队列

```text
GET    /api/v1/queue/
POST   /api/v1/queue/
GET    /api/v1/queue/{item_id}
PATCH  /api/v1/queue/{item_id}
DELETE /api/v1/queue/{item_id}
POST   /api/v1/queue/{item_id}/start
POST   /api/v1/queue/{item_id}/cancel
POST   /api/v1/queue/{item_id}/stop
POST   /api/v1/queue/reorder
PATCH  /api/v1/queue/bulk
POST   /api/v1/queue/batches
GET    /api/v1/queue/batches
```

BCA 任务排队后，使用原生队列接口读取和控制，不重复实现队列状态机。

### 9.3 Library

```text
GET    /api/v1/library/files/
POST   /api/v1/library/files/
GET    /api/v1/library/files/{file_id}
PUT    /api/v1/library/files/{file_id}
DELETE /api/v1/library/files/{file_id}
GET    /api/v1/library/files/{file_id}/download
GET    /api/v1/library/files/{file_id}/thumbnail
GET    /api/v1/library/files/{file_id}/plates
POST   /api/v1/library/files/{file_id}/slice
POST   /api/v1/library/files/{file_id}/print
POST   /api/v1/library/files/add-to-queue
```

只有包含 `Metadata/plate_N.gcode` 和 `Metadata/slice_info.config` 的切片包才具备进入打印队列的条件。仅有 `[Content_Types].xml` 和 `3D/*.model` 的模型包不是 printer-ready 文件。

### 9.4 Archive、Project、耗材库存

```text
# Archive
GET/PATCH/DELETE /api/v1/archives/{archive_id}
GET              /api/v1/archives/
POST             /api/v1/archives/upload
POST             /api/v1/archives/{archive_id}/reprint
GET              /api/v1/archives/{archive_id}/plates

# Project
GET/POST         /api/v1/projects/
GET/PATCH/DELETE /api/v1/projects/{project_id}
GET              /api/v1/projects/{project_id}/archives
GET              /api/v1/projects/{project_id}/queue

# Inventory
GET/POST         /api/v1/inventory/spools
GET/PATCH/DELETE /api/v1/inventory/spools/{spool_id}
POST             /api/v1/inventory/spools/{spool_id}/archive
POST             /api/v1/inventory/spools/{spool_id}/restore
GET              /api/v1/inventory/assignments
POST             /api/v1/inventory/assignments
```

BCA 多色校准读取的是活跃 Bambuddy spool 库，不读取 `color_catalog` 作为实际库存替代品。

### 9.5 Webhook

Webhook 使用 API Key，并按 API Key 的 printer scope 限制打印机：

```text
POST /api/v1/webhook/queue/add
POST /api/v1/webhook/printer/{printer_id}/start
POST /api/v1/webhook/printer/{printer_id}/stop
POST /api/v1/webhook/printer/{printer_id}/cancel
GET  /api/v1/webhook/printer/{printer_id}/status
GET  /api/v1/webhook/queue
```

加入队列请求：

```json
{
  "archive_id": 10,
  "printer_id": 1,
  "project_id": null,
  "scheduled_time": "2026-01-01T12:00:00Z",
  "require_previous_success": false,
  "auto_off_after": false
}
```

该接口需要 `can_queue`；start/stop/cancel 需要 `can_control_printer`。不存在 Archive/Printer 返回 404；时间格式错误返回 400；没有待打印项或打印机未连接时按具体接口返回 404/503/409。

## 10. WebSocket 实时事件

### 10.1 建立连接

```text
WS {ORIGIN}/api/v1/ws?token=<websocket-token>
```

认证关闭时可省略 token。认证开启时，先调用：

```http
POST /api/v1/auth/ws-token
Authorization: Bearer <JWT-or-api-key>
```

响应：

```json
{"token":"<opaque-token>"}
```

token 有效期 60 分钟。缺失、无效或过期 token 会在 accept 之前关闭连接，关闭码为 `4401`。不要把普通 JWT 或 API Key 直接放进 WebSocket URL。

### 10.2 客户端消息

保活：

```json
{"type":"ping"}
```

响应：

```json
{"type":"pong"}
```

请求某台打印机状态：

```json
{"type":"get_status","printer_id":1}
```

### 10.3 服务端消息

初次连接及状态变化会收到：

```json
{
  "type": "printer_status",
  "printer_id": 1,
  "data": {}
}
```

原生事件还可能包括 `print_start`、`print_complete`、`archive_created`、`archive_updated`、`inventory_changed` 等，客户端必须忽略未知事件类型。

BCA 阶段事件：

```json
{
  "type": "bca_creator_session",
  "session_id": "...",
  "stage": "images|model|analysis|calibration",
  "event": "running|updated|failed",
  "status": "...",
  "image_count": 4,
  "print_file_status": "...",
  "color_calibration_status": "..."
}
```

WebSocket 只是通知通道，不是状态数据库。收到 BCA 事件后，应按 `session_id` 过滤，再重新 GET session snapshot；事件丢失时轮询仍可恢复状态。

## 11. 原生 Bambuddy 接口资源索引

当前运行实例的 OpenAPI 暴露全部资源和精确 schema。以下是资源标签和本文覆盖的常用接口索引，不等同于逐 path 的全量字段契约。对未在第 9 节展开的原生接口，请直接读取 OpenAPI 的 `requestBody`、`parameters`、`responses` 和 `security`。

本文没有固化全量路由目录，因此不会因为部署后的源码路由变化产生过期快照。若需要 route-level 目录，应从目标版本源码/运行实例重新生成，仅记录 `path`、`method`、`tag` 和鉴权 scheme；字段契约仍以同一实例的 OpenAPI 为准。

| 标签 | 资源前缀 | 用途 |
|---|---|---|
| `authentication`、`2fa`、`oidc` | `/api/v1/auth` | 登录、2FA、OIDC、token |
| `creator`、`creator-modules` | `/api/v1/creator` | BCA 会话与直接模块 |
| `bca-tasks` | `/api/v1/bca-tasks` | 任务、切片、队列交接 |
| `printers`、`camera`、`kprofiles` | `/api/v1/printers` | 打印机状态、控制、相机、校准 |
| `queue` | `/api/v1/queue` | 原生打印队列 |
| `library`、`library-tags`、`library-trash`、`library-variants` | `/api/v1/library` | 文件、标签、回收站、变体 |
| `archives`、`archives-purge` | `/api/v1/archives` | 打印归档、分析、导出、清理 |
| `projects` | `/api/v1/projects` | 项目、附件、BOM、模板 |
| `inventory`、`spoolman`、`spoolman-inventory` | `/api/v1/inventory` 或 `/api/v1/spoolman` | spool、颜色、AMS 分配、Spoolman |
| `webhook` | `/api/v1/webhook` | 外部自动化队列和控制 |
| `discovery` | `/api/v1/discovery` | 打印机发现和子网扫描 |
| `settings`、`system` | `/api/v1/settings`、`/api/v1/system` | 系统配置和状态 |
| `users`、`groups`、`api-keys` | `/api/v1/users` 等 | 管理员资源 |
| `notifications`、`notification-templates` | `/api/v1/notifications` | 通知与模板 |
| `maintenance` | `/api/v1/maintenance` | 维护计划和履历 |
| `firmware`、`updates` | `/api/v1/firmware`、`/api/v1/updates` | 固件和应用更新 |
| `local-backup`、`github-backup` | `/api/v1/*-backup` | 备份与恢复 |
| `smart-plugs`、`ha-sensors` | `/api/v1/smart-plugs` 等 | 智能插座与 Home Assistant |
| `spoolbuddy` | `/api/v1/spoolbuddy` | NFC、秤、设备诊断和更新 |
| `cloud`、`orca-cloud`、`makerworld` | `/api/v1/*` | 第三方云和 MakerWorld |

OpenAPI 会随源码版本更新，客户端生成 SDK 时应在目标部署实例上拉取：

```bash
curl -fsS "$ORIGIN/openapi.json" -o openapi.json
```

不要根据本文的资源索引猜测未列出的请求体或权限；使用 schema 中的 `requestBody`、`parameters`、`responses` 和 `components.schemas`。

## 12. 权限与最小权限建议

JWT 用户请求按用户组权限执行；认证关闭时，应用按单用户本地部署逻辑放行。认证开启后，缺少凭据的受保护请求返回 401，凭据有效但权限不足返回 403。

建议为自动化拆分 API Key：

1. 状态看板：仅 `can_read_status`，限制 `printer_ids`；
2. 排队机器人：`can_read_status` + `can_queue`，不授予硬件控制；
3. 打印控制机器人：在确有需要时增加 `can_control_printer`；
4. 耗材同步：仅增加 `can_manage_inventory`；
5. BCA 对接：按实际是否需要创作、任务上传、读取产物分配 `can_queue`、`can_manage_library` 和读状态权限。

永远不要为了“让接口先跑通”使用管理员 JWT 或全权限 Key。

## 13. 端到端对接示例

以下流程展示一个不包含真实凭据的客户端骨架：

```bash
BASE="http://127.0.0.1:8000"
# Windows bridge 部署改为 http://127.0.0.1:8012
TOKEN="<JWT-or-api-key>"

# 1. 准备 brief
curl -fsS "$BASE/api/v1/creator/modules/brief/prepare" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"一个低多边形桌面摆件","current_brief":{},"has_reference_image":false}'

# 2. 生成风格图（真实调用可能产生费用）
curl -fsS "$BASE/api/v1/creator/modules/image2/generate" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'prompt=validated prompt from step 1' \
  -o style.png

# 3. 用 style.png 生成 GLB（真实调用可能产生费用）
curl -fsS "$BASE/api/v1/creator/modules/model/generate" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'image=@style.png;type=image/png' \
  -o model.glb

# 4. 将 GLB 转换为多色模型 3MF（真实调用可能产生费用）
curl -fsS "$BASE/api/v1/creator/modules/print/multicolor" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'model=@model.glb;type=model/gltf-binary' \
  -F 'max_colors=4' \
  -o multicolor.3mf

# 5. 按活跃 Bambuddy spool 库校准该模型 3MF（真实调用可能产生费用）
curl -fsS "$BASE/api/v1/creator/modules/print/calibrate" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'file=@multicolor.3mf;type=model/3mf' \
  -o calibrated.3mf

# 6. 将已校准模型交给 BCA task，等待 root 切片

curl -fsS "$BASE/api/v1/bca-tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'file=@calibrated.3mf;type=model/3mf' \
  -F 'title=桌面摆件'
```

实际生产流程必须检查每一步 HTTP 状态、Content-Type、文件完整性和业务状态；不要只检查 curl 是否退出 0。

## 14. 安全、费用与数据一致性

- Provider 凭据只通过受保护的 Creator config PUT 写入，GET 永不回显；
- 不要把凭据、API Key、客户电话地址或完整模型写入普通日志；
- 付费 Provider POST 不自动重试。网络断开时请求可能已经计费；
- 日常测试使用非计费 readiness 检查；付费 smoke 必须在执行具体阶段前取得明确运维批准；
- Creator 产物通过受保护 BCA 路由下载，不暴露本地文件路径；
- BCA 模型 3MF 和切片 3MF 都受 512 MiB 及 ZIP 安全限制；
- 模型 3MF 绝不能跳过 root 切片直接入队；
- 备份必须同时包含数据库和 `DATA_DIR`，以保持 Creator 产物、任务源文件、Library 和队列关系一致；
- 当前 BCA 使用进程内锁和任务映射，不要运行多 Uvicorn worker 或多个 BCA 副本；
- Meshy webhook authenticity 未建立前，不要自建或接受未经验证的 Meshy webhook 状态回调。

## 15. 对接验收清单

- [ ] 能读取 `/health`，且部署拓扑使用正确端口；
- [ ] 能用最小权限 JWT/API Key 调用目标接口；
- [ ] 未授权请求得到 401，权限不足得到 403；
- [ ] 客户端兼容字符串、数组、对象三种错误 detail；
- [ ] 文件上传使用 multipart，不手工固定 boundary；
- [ ] 3MF 上传前后检查扩展名、响应类型和大小；
- [ ] Creator 异步接口收到 202 后轮询 snapshot；
- [ ] WebSocket 事件只作为刷新提示，snapshot 作为最终状态；
- [ ] 任务先处于 `awaiting_slice`，root 上传验证通过的 `.gcode.3mf` 后才进入 `ready_for_queue`；
- [ ] 只将 `ready_for_queue` 任务加入原生队列；
- [ ] 生产反向代理已验证大型 3MF 的 Content-Length、SHA-256 和 WebSocket；
- [ ] 未在日志、Git、文档或错误上报中泄露任何真实凭据。
