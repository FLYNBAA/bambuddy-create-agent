# BCA 部署指南

[English](DEPLOYMENT_BCA.md) | **中文**

BCA 作为 Bambuddy 的一部分部署：一个应用、一个前端 origin，并由 Bambuddy 继续负责身份、队列和打印机。不要将第二个 create-agent 服务、独立 Agent 对话 UI 或上游预构建镜像描述为当前 BCA 部署。

## 1. 支持的 Compose 拓扑

### Linux 打印机 LAN 部署

Linux Compose 从本地仓库源码构建 `bambuddy-bca:local`。使用显式 BCA 环境文件，而不是隐式项目 dotenv 发现：

```bash
docker compose --env-file .env.bca up -d --build
```

Linux 拓扑使用 host networking，并保留用于打印机 LAN 发现的 SSDP。`.env.bca` 提供部署初始值；它不能替代安全凭据管理，也不得提交。

### Windows Docker Desktop 或其他 bridge 部署

使用 bridge override 及声明的发现目标集：

```powershell
docker compose --env-file .env.bca -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d --build
```

将 `BCA_DISCOVERY_SUBNETS` 设置为允许 BCA 扫描的 CIDR，例如相关私有 LAN，必要时还包括 Tailscale CGNAT 范围。bridge 部署使用单播扫描，不依赖 SSDP 广播发现。适用时可直接添加打印机 LAN IP。不得暗示 bridge 模式具有 host-network multicast 行为。

日常停机和移除使用普通 Compose 操作。需要保留部署数据时，不要删除数据卷。

## 2. Provider 配置

`/creator/settings` 的 Creator 配置可编辑非秘密运行参数，并接受 DeepSeek、Image2、Hunyuan 和 Meshy 的只写凭据替换。`GET /api/v1/creator/config` 永不返回凭据，只返回运行参数和 `configured` 状态。显式 `.env.bca` 提供部署初始值；BCA 不读取 source-project `.env` 或 `.env.local`。

持久化 Creator 配置仍是敏感数据库状态。配置页、数据库、备份和 `.env.bca` 都必须在管理员控制下。不要把凭据放入任务记录、预览、源码或公开文档。

公网集成应使用工作目录的 `BCA_INTEGRATION_GUIDE.md` 说明的独立 `/api/v1/creator/modules/*` 能力路由。`/creator` 页面是逐请求测试台，不是工作流编排器。

## 3. 反向代理与公网 origin

仓库中的生产 Nginx 模板为 [`deploy/nginx/bca.conf`](deploy/nginx/bca.conf)。用它作为静态应用服务及 API/WebSocket 到 Bambuddy 代理的拓扑参考。它保留上游认证和 forwarded 头，为产物/上传关闭代理缓冲，并设置 1000 秒 API 读/发送超时，因为 Meshy/Hunyuan 模块调用可持续至 900 秒。

上线前必须通过已部署的 HTTPS/Nginx origin 下载受认证的大型 3MF，并把 `Content-Length` 与 SHA-256 和持久化文件逐一比较。进程内 FastAPI 测试不足以验证代理路径。

## 4. Tailscale 与发现

Tailscale 提供网络可达性，不提供应用认证、TLS 证书或打印机 LAN 路由。仍应保留 Bambuddy 认证与 API Key 控制。要访问另一 LAN 后的打印机，应部署外部维护的 Tailscale 子网路由器，或让 BCA 运行在该打印机 LAN。BCA 不会自动注册为子网路由器，也不会自行通告路由。

## 5. 工作流、任务与原生队列交接

直接工作流为：创意展示（DeepSeek）→ 风格图（Image2）→ 3D 概念图/模型（Hunyuan）→ 白色或 1–8 色校准（Meshy 加耗材颜色匹配）→ Meshy + DeepSeek 评分/洞察且不提供建议 → 订单任务提交。

任务在等待 root 切片和排队时保留标题、用户、姓名、手机号、地址、备注、可选价格（会话推送或直传任务时提供）、风格图和内嵌彩色 3MF 快照。任务清单响应保留 `source_3mf_url` 用于下载完整 3MF，`source_3mf_snapshot_url` 指向 `GET /api/v1/bca-tasks/{id}/snapshot`（只返回内嵌 `Metadata/plate_1.png`，缺失时 404）。直传 `POST /api/v1/bca-tasks` 接受模型 `.3mf`，拒绝 GLB 与切片 `.gcode.3mf`。

```text
Metadata/plate_N.gcode
Metadata/slice_info.config
```

验证后交接给 Bambuddy 原生 Library/队列；打印机控制和队列生命周期继续由 Bambuddy 负责。

## 6. 备份、恢复与回滚

创建一个同时包含下列内容的恢复点：

1. `DATA_DIR`，包括 Creator 产物和任务源文件。
2. 匹配的 Bambuddy 数据库，包括持久化 Provider 配置和 Library/队列关系。

必须一起恢复。只恢复数据文件或只恢复数据库都可能让任务和产物脱离原生 Library/队列记录。源码回滚必须使用已知兼容的本地源码修订；数据兼容性不明确时，恢复匹配恢复点，而不要将旧源码与较新数据混用。

## 7. 验证指导

应通过实际拓扑验证部署行为：应用健康端点、经配置代理的认证应用访问、预期发现方式（Linux host networking 的 SSDP 或 bridge 的声明子网单播）及 root 切片到原生队列的交接。这些检查不需要计费 Provider。

日常验证不得调用计费 Provider。计费 Provider smoke 运行必须在该次调用及其费用被授权时取得明确人工批准。这是该运行的运维批准，不是产品 UI 付费确认门；UI 也没有问题确认门。打印分析只返回评分和洞察，不提供建议。

## 相关文档

- [English deployment guide](DEPLOYMENT_BCA.md)
- [架构说明](BCA_ARCHITECTURE.zh-CN.md)
- [中文 README](README.md)
- [文档审计](DOCUMENTATION_AUDIT.zh-CN.md)
