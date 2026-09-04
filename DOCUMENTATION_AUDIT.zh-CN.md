# 文档审计

[English](DOCUMENTATION_AUDIT.md) | **中文**

## 范围与双语文档

本清单覆盖定义 BCA 当前工作流、配置、架构、部署和前端行为的 BCA 专用 Markdown 文档。英文与中文文档在文首互相配对：

| English | 中文 | 当前用途 |
|---|---|---|
| [README.en.md](README.en.md) | [README.md](README.md) | BCA 直接工作流、运行边界、拓扑摘要、恢复与计费运行批准策略。 |
| [BCA_ARCHITECTURE.md](BCA_ARCHITECTURE.md) | [BCA_ARCHITECTURE.zh-CN.md](BCA_ARCHITECTURE.zh-CN.md) | 工作流职责、任务交接、配置、安全、持久化与系统边界。 |
| [DEPLOYMENT_BCA.md](DEPLOYMENT_BCA.md) | [DEPLOYMENT_BCA.zh-CN.md](DEPLOYMENT_BCA.zh-CN.md) | 本地源码 Compose 部署、发现、代理拓扑、Tailscale 边界、恢复、回滚与验证。 |
| [frontend/README.md](frontend/README.md) | [frontend/README.zh-CN.md](frontend/README.zh-CN.md) | 内嵌前端页面和 BCA UI/数据契约。 |
| [DOCUMENTATION_AUDIT.md](DOCUMENTATION_AUDIT.md) | [DOCUMENTATION_AUDIT.zh-CN.md](DOCUMENTATION_AUDIT.zh-CN.md) | 本审计清单与过时声明替换记录。 |
| [AGENTS.md](AGENTS.md) | [AGENTS.zh-CN.md](AGENTS.zh-CN.md) | Creator、产物、快照、任务 API 与运行限制的工程契约。 |
| [SECURITY.en.md](SECURITY.en.md) | [SECURITY.md](SECURITY.md) | BCA 安全、提示词、产物和上传边界契约。 |
| [CONTRIBUTING.en.md](CONTRIBUTING.en.md) | [CONTRIBUTING.md](CONTRIBUTING.md) | BCA 状态、API、前端和文档改动的贡献要求。 |
| [docs/onboarding-tour-plan.en.md](docs/onboarding-tour-plan.en.md) | [docs/onboarding-tour-plan.md](docs/onboarding-tour-plan.md) | BCA 管理引导顺序与不计费运行边界。

## 当前跨文档契约

- BCA 直接顺序为：源语言创意扩充 → Image2 → 3D 概念图/模型 → 以 Meshy 和耗材颜色匹配执行白色或 1–8 色校准 → 最终颜色校准 3MF → Meshy + DeepSeek 评分/洞察且不提供建议 → 订单任务提交。
- 任务等待 root 切片和原生排队时保留标题、用户、订单字段、可选价格、风格图和内嵌彩色 3MF 快照。`source_3mf_url` 下载完整模型，`source_3mf_snapshot_url` 只返回 `Metadata/plate_1.png`；Task UI 从不渲染完整模型几何。模型 3MF 不能直接打印；root 提供通过验证的切片 `.gcode.3mf`。
- brief 响应全程跟随最新消息语言，并始终自动补全最终 `positive_prompt`、`negative_prompt`、`print_constraints` 和确定性的 `image2_prompt`。不存在追问/类型选择路径；兼容字段 `questions` 为空，直接测试台将 `image2_prompt` 带入 Image2。
- GLB 只在 Creator 中以原生材质交互式渲染；BCA 3MF 预览使用内嵌的 512×512 彩色 `Metadata/plate_1.png` 快照。多色与校色分别返回 `X-BCA-Color-Snapshot`（`created|present|skipped`、`replaced|skipped`）；快照是 best-effort 且 fail-open。
- 校准库存是符合条件的活动 `spool` 数据，不是 `color_catalog`。任何“多色校准成功”声明必须同时具备 succeeded、非空 assignments 和最终校准产物。
- 工作目录的 `BCA_INTEGRATION_GUIDE.md` 是外部 REST 契约，包含任务 source/snapshot URL 与独立模块响应头。
- Creator 配置可编辑 Provider 请求端点/Base URL，包括 Meshy Base URL，以及凭据与模型设置。显式 `.env.bca` 提供部署初始值；source-project `.env` 与 `.env.local` 不是 BCA 配置输入。
- Linux Compose 从本地 BCA 源码构建 `bambuddy-bca:local` 并使用显式 `.env.bca`。Linux host networking 保留 SSDP。Windows 与 bridge 部署使用声明的 `BCA_DISCOVERY_SUBNETS` CIDR 和单播扫描。
- 支持的 Nginx 模板是 [`deploy/nginx/bca.conf`](deploy/nginx/bca.conf)；它保留上游认证，并转发 WebSocket 和 forwarded-request 头。
- Tailscale 只提供可达性。打印机 LAN 访问需要外部子网路由器，或将 BCA 与打印机同置 LAN。BCA 不会自动注册为子网路由器，也不提供证书。
- 备份/恢复把 `DATA_DIR` 与匹配的 Bambuddy 数据库作为同一恢复点。回滚使用已知兼容的本地源码修订，或恢复该匹配恢复点。
- 产品 UI 没有付费确认门或问题确认门。计费 Provider smoke 运行必须在执行时对具体调用及费用取得明确人工批准。

## 已淘汰的过时声明

目标文档不得将下列内容描述为当前 BCA 行为：

| 已淘汰声明 | 当前替代 |
|---|---|
| Creator 图像、3D、校准或分析卡片前有确认/付费门。 | 产品 UI 没有付费或问题确认门；计费运维运行在调用时需要人工批准。 |
| 非健康报告会因用户问题确认而阻塞。 | 分析只报告评分和洞察，不提供建议，也没有问题确认门。 |
| 四图 GPT Image 流程或独立 Agent 聊天 UI。 | 文档工作流使用含 DeepSeek、Image2 与 Hunyuan 的独立 Creator API 模块。 |
| Provider 端点固定或 Meshy Base URL 不可配置。 | Creator 配置可编辑每个 Provider 请求端点/Base URL，包括 Meshy。 |
| 当前 BCA 拉取上游预构建 Docker 镜像或隐式发现 dotenv。 | Compose 构建本地源码 `bambuddy-bca:local` 并使用显式 `.env.bca`。 |
| bridge 部署依赖 SSDP 广播。 | bridge 部署对声明的 `BCA_DISCOVERY_SUBNETS` 进行单播扫描；Linux host networking 保留 SSDP。 |
| Tailscale 会自动让 BCA 成为子网路由器或提供证书。 | 运维方提供外部路由/证书，或将 BCA 同置于打印机 LAN。 |
| 任意 Nginx 配置都是参考生产拓扑。 | `deploy/nginx/bca.conf` 是支持的 BCA 生产模板，含上游认证与 WebSocket/forwarded-header 支持。 |
| 备份或回滚可以分别恢复数据库和数据。 | 必须一起恢复匹配的数据库与 `DATA_DIR` 恢复点。 |

## 范围外文档

通用 Bambuddy 历史、治理或上游派生文档不是 BCA 行为依据，除非本清单明确链接。它们不得覆盖这些 BCA 双语文档。
