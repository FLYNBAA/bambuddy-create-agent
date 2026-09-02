# BCA 架构说明

[English](BCA_ARCHITECTURE.md) | **中文**

## 范围

BCA 是 Bambuddy 内嵌的创作 API 功能层。身份、打印机、耗材、Library 文件、原生队列交接、认证、WebSocket 传输和部署均由 Bambuddy 唯一负责。Creator 对外暴露可独立调用的 brief、Image2、图生 GLB、GLB 转 3MF、3MF 校色和分析模块；旧会话只保留为兼容适配器，不再是公网集成模型。

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

### 源语言提示词契约

最新创意消息决定整个响应语言：中文输入返回中文 brief、问题、展示文案和提示词包；英文输入则全部为英文。`subject`、`style`、`product_type` 全部完成后，BCA 派生 `positive_prompt`、`negative_prompt`、`print_constraints` 及确定性的 `image2_prompt`。固定 Image2 条款明确构图、可打印性、排除项和输出边界；测试台展示完整提示词包，并将 `image2_prompt` 自动带入 Image2 输入框。

## Creator 与任务职责

| 范围 | 职责 |
|---|---|
| Creator API 模块 | 执行一个明确请求的能力；绝不为调用方创建或推进工作流。 |
| Creator 测试台 | 发送单个模块请求，展示原始响应元数据/JSON，并预览返回的图片或模型产物。 |
| 校准 | 将 GLB 转换为 1–8 色 3MF，再独立将 3MF 颜色匹配到 Bambuddy 耗材库存。 |
| 分析 | 获取 Meshy 数据及 DeepSeek 评分/洞察；不生成面向用户的建议。 |
| BCA 任务 | 旧交接：在 root 附加已验证切片并选择打印机前保留标题、用户、订单和预览。 |
| Bambuddy | 负责 Library 文件、打印机选择、队列生命周期、派发、取消和打印机状态。 |

## API 与配置边界

Creator 与任务路由仍在 Bambuddy 授权模型中。公网模块客户端使用 queue 范围 API Key；普通产物下载受控；Provider 临时 URL 和服务器文件系统路径绝不是前端契约。

`/creator/settings` 仅管理员可访问。Provider 密钥为只写：`GET` 返回非秘密运行参数和 `configured` 状态，`PUT` 可替换密钥但绝不回显。部署值通过显式 `.env.bca` 提供初始配置；BCA 不会发现或读取 source-project `.env` / `.env.local` 文件。

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
