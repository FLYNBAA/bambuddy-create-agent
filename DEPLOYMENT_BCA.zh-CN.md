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

`/creator/settings` 的 Creator 配置可编辑 DeepSeek、Image2、Hunyuan 和 Meshy 的凭据、模型及 Provider 请求端点/Base URL；Meshy Base URL 可配置。显式 `.env.bca` 提供部署初始值；BCA 不读取 source-project `.env` 或 `.env.local`。

持久化 Creator 配置是敏感数据库状态。配置页、数据库、备份和 `.env.bca` 都必须在管理员控制下。不要把凭据放入任务记录、预览、源码或公开文档。

## 3. 反向代理与公网 origin

仓库中的生产 Nginx 模板为 [`deploy/nginx/bca.conf`](deploy/nginx/bca.conf)。用它作为静态应用服务及 API/WebSocket 到 Bambuddy 代理的拓扑参考。它保留上游认证，并转发 WebSocket 与 forwarded-request 头。

使用 `MESHY_MODEL_INPUT_MODE=public_url` 时，将 `BCA_PUBLIC_BASE_URL` 设置为可从外部访问、且代理受控模型路由的 HTTPS origin。反向代理、DNS、证书签发和可信 forwarded-header 策略均由运维基础设施负责。不得声称 BCA 会提供证书或信任任意 forwarded headers。

## 4. Tailscale 与发现

Tailscale 提供网络可达性，不提供应用认证、TLS 证书或打印机 LAN 路由。仍应保留 Bambuddy 认证与 API Key 控制。要访问另一 LAN 后的打印机，应部署外部维护的 Tailscale 子网路由器，或让 BCA 运行在该打印机 LAN。BCA 不会自动注册为子网路由器，也不会自行通告路由。

## 5. 工作流、任务与原生队列交接

直接工作流为：创意展示（DeepSeek）→ 风格图（Image2）→ 3D 概念图/模型（Hunyuan）→ 白色或 1–8 色校准（Meshy 加耗材颜色匹配）→ Meshy + DeepSeek 评分/洞察且不提供建议 → 订单任务提交。

任务在等待 root 切片和排队时保留标题、用户、姓名、手机号、地址、备注、当前留空的可空价格，以及模型/风格预览。模型 3MF 不能直接打印。root 附加的 slicer 生成 `.gcode.3mf` 必须包含：

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
