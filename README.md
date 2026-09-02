# Bambuddy Create Agent（BCA）

[English](README.en.md) | **中文**

BCA 是嵌入 Bambuddy 的 3D 创作工作流。用户、打印机、耗材、Library 文件、队列、认证与部署均以 Bambuddy 为准；BCA 不是第二个 create-agent 服务，也不是独立的 Agent 对话 UI。

## 直接工作流

```text
创意展示（DeepSeek）
  → 风格图生成（Image2）
  → 3D 概念图/模型生成（Hunyuan）
  → 打印校准
      白色，或使用 Meshy 与耗材颜色匹配的 1–8 色多色校准
      → 最终颜色校准 3MF
  → 打印分析（Meshy + DeepSeek 评分与洞察；不提供建议）
  → 订单任务提交
  → root 切片并交接原生队列
```

BCA 以对外 API 功能层运行，不再要求 Creator 卡片工作流。`/creator` 是逐模块测试台：它发起一个独立能力请求、展示数据窗口，并预览返回图片或 GLB/3MF。公网程序按需组合 brief、Image2、图生模型、多色转换、校色和分析；模型 3MF 仍不是打印任务，打印交接由 root 的 `.gcode.3mf` 与 Bambuddy 原生队列负责。

GLB 预览保留原生材质；3MF 使用 Three.js 官方 `ThreeMFLoader` 解析标准材质/颜色/纹理组，并在根节点从 Z-up 转为 WebGL 的 Y-up。Image2 生成结果统一为不拉伸主体的 1:1 PNG。

有效切片包必须同时包含：

```text
Metadata/plate_N.gcode
Metadata/slice_info.config
```

## BCA 页面

| 页面 | 路由 | 当前职责 |
|---|---|---|
| Creator | `/creator` | 独立 API 模块测试台：请求、原始数据窗口、图片/模型预览。 |
| BCA Tasks | `/tasks` | 旧任务标题/订单上下文、root 切片附件、打印机选择和原生队列提交。 |
| Creator 配置 | `/creator/settings` | 只写 Provider 密钥、非秘密运行参数和 Provider 状态。 |
| Bambuddy 原生页面 | 打印机、耗材、Library、队列 | 唯一权威的打印机、耗材、Library 与队列行为。 |

认证开启时，预览使用受控的 Bearer Blob fetch；不要暴露 Provider 临时 URL，也不要把受保护的产物路由直接作为 `<img src>`。

## Provider 配置

Creator 配置只会返回非秘密运行参数和 Provider 状态；密钥仅可写入、绝不通过 GET 或保存响应回显。部署初始值来自显式 `.env.bca`；BCA 不读取 source-project `.env` 或 `.env.local`。持久化的 Creator 配置属于敏感数据库数据，必须按凭据处理。

## 部署与发现

- Linux Compose 从本地 BCA 源码构建本地 `bambuddy-bca:local` 镜像，并使用显式 `.env.bca` 文件。
- Linux host-network 部署保留打印机局域网的 SSDP 发现。
- Windows Docker Desktop 和其他 bridge 部署使用声明的 `BCA_DISCOVERY_SUBNETS` CIDR 与单播扫描，不依赖广播发现。
- Tailscale 只提供连通性。通过外部维护的子网路由器访问打印机 LAN，或将 BCA 与打印机部署在同一 LAN。BCA 不会自行注册为子网路由器，也不提供证书。
- 生产反向代理模板是 [`deploy/nginx/bca.conf`](deploy/nginx/bca.conf)，它保留上游认证并转发 WebSocket 和 forwarded-request 头。

支持的生产拓扑、恢复、回滚和验证步骤见[部署指南](DEPLOYMENT_BCA.zh-CN.md)。

## 备份与回滚

将 `DATA_DIR` 与 Bambuddy 数据库作为同一个匹配恢复点备份。其中包含 Creator 产物、任务源文件、Library/队列关系和持久化 Provider 配置。回滚时使用已知兼容的本地源码修订；若数据兼容性不明确，必须同时恢复匹配的数据库与 `DATA_DIR` 恢复点，不得单独恢复其中之一。

## 计费 Provider smoke 策略

产品 UI 没有付费确认门或问题确认门。日常检查不得调用计费 Provider。只有人在调用时对该次运行及相关费用作出明确批准，才可调用计费 Provider；不得将先前的 UI 操作或可复用标志视为产品确认。打印分析只报告评分和洞察，不提供建议。

## 当前边界

BCA 当前为单进程。不得声称支持多 worker、分布式队列恢复、多用户所有权隔离、自动 Tailscale 子网路由或自动 TLS/证书配置。

## 相关文档

- [English README](README.en.md)
- [架构说明](BCA_ARCHITECTURE.zh-CN.md)
- [部署指南](DEPLOYMENT_BCA.zh-CN.md)
- [文档审计](DOCUMENTATION_AUDIT.zh-CN.md)
- [前端说明](frontend/README.zh-CN.md)
