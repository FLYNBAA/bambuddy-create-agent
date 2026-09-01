# BCA 架构说明

[English](BCA_ARCHITECTURE.md) | **中文**

## 范围

BCA 是 Bambuddy 内嵌的单进程创作工作流。身份、打印机、耗材、Library 文件、原生队列交接、认证、WebSocket 传输和部署均由 Bambuddy 唯一负责。BCA 管理创作状态、生成产物、校准、分析和订单任务交接；它不是独立服务，也不是独立 Agent 对话 UI。

## 工作流与交接

```text
创意展示（DeepSeek）
  → 风格图（Image2）
  → 3D 概念图/模型（Hunyuan）
  → 校准：白色或 1–8 色多色
      Meshy + Bambuddy 耗材颜色匹配 → 颜色校准 3MF
  → 分析：Meshy + DeepSeek 评分与洞察，不提供建议
  → 订单任务提交
  → root 附加通过验证的切片 .gcode.3mf
  → Bambuddy LibraryFile 与原生 PrintQueueItem
```

任务在等待 root 切片和排队时保留标题、用户、姓名、手机号、地址、备注、可空价格（当前留空），以及模型/风格预览。Creator 模型 3MF 绝不直接发送到打印机。root 提供的切片包必须包含 `Metadata/plate_N.gcode` 与 `Metadata/slice_info.config`，BCA 才能交给原生队列。

## Creator 与任务职责

| 范围 | 职责 |
|---|---|
| Creator 卡片 | 运行直接分阶段工作流；展示风格和模型预览；创建校准产物、分析和订单任务。 |
| 校准 | 生成白色 3MF，或以 Meshy 与 Bambuddy 耗材颜色匹配生成 1–8 色 3MF；最终多色输出是颜色校准 3MF。 |
| 分析 | 获取 Meshy 数据及 DeepSeek 评分/洞察；不生成面向用户的建议。 |
| BCA 任务 | 在 root 附加已验证切片并选择打印机前保留标题、用户、订单和预览。 |
| Bambuddy | 负责 Library 文件、打印机选择、队列生命周期、派发、取消和打印机状态。 |

## API 与配置边界

Creator 和任务路由仍在 Bambuddy 应用与其授权模型中。普通产物下载受控；Provider 临时 URL 和服务器文件系统路径不是前端契约。

Creator 配置页（`/creator/settings`）可更新 DeepSeek、Image2、Hunyuan 与 Meshy 的 Provider 凭据、模型和请求端点/Base URL，包括 Meshy Base URL。部署值通过显式 `.env.bca` 提供初始配置；BCA 不会发现或读取 source-project `.env` / `.env.local`。持久化 Provider 设置是敏感 Bambuddy 数据库数据。

## 批准与安全边界

产品 UI 没有付费确认门或问题确认门。日常验证不会调用计费 Provider。任何计费 Provider 运行都必须在执行点由人对该次调用及其费用明确批准。这一运维批准不是工作流卡片门。打印分析只提供评分和洞察，不提供建议。

## 部署边界

Linux Compose 从本地源码构建 `bambuddy-bca:local` 并使用显式 `.env.bca`。Linux host networking 保留 SSDP 发现。Windows Docker Desktop 和其他 bridge 网络使用声明的 `BCA_DISCOVERY_SUBNETS` CIDR 与单播扫描。

公网 origin 或 Meshy public-URL 输入使用 `deploy/nginx/bca.conf` 生产反向代理模板。它保留上游认证，并转发 WebSocket 与 forwarded-request 头。Tailscale 只提供网络连通性：打印机 LAN 访问需要外部子网路由器，或将 BCA 与打印机部署在同一 LAN。BCA 不会自动注册为子网路由器，也不提供证书。

## 持久化、恢复与限制

必须将匹配的 `DATA_DIR` 与 Bambuddy 数据库一起备份和恢复：Creator 产物、任务源文件、持久化配置和 Library/队列关系不得脱节。仅回滚到已知兼容的本地源码修订；若兼容性不明确，恢复匹配恢复点。

当前实现仍为单进程。多 worker 调度、分布式锁、持久 worker 恢复、多用户所有权隔离、对象存储和可验证 Provider webhook 均不是当前行为。

## 相关文档

- [English architecture](BCA_ARCHITECTURE.md)
- [部署指南](DEPLOYMENT_BCA.zh-CN.md)
- [中文 README](README.md)
- [文档审计](DOCUMENTATION_AUDIT.zh-CN.md)
