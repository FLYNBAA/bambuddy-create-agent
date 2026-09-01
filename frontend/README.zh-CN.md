# Bambuddy 前端

[English](README.md) | **中文**

React + TypeScript + Vite 前端构建到仓库根目录 `static/`，由 Bambuddy 应用提供服务。BCA 始终内嵌在该应用中；不要创建第二个应用外壳、独立生产前端或独立 Agent 对话页面。

## BCA 页面

| 路由 | 组件 | 当前职责 |
|---|---|---|
| `/creator` | `pages/CreatorPage.tsx` | 用于 DeepSeek 创意展示、Image2 风格图、Hunyuan 3D 概念图/模型生成、校准、分析和订单任务提交的直接 Creator 卡片。 |
| `/tasks` | `pages/TaskListPage.tsx` | 保留标题、用户、姓名、手机号、地址、备注、当前留空价格及模型/风格预览，接收 root 切片、选择打印机并提交到 Bambuddy 原生队列。 |
| `/creator/settings` | `pages/CreatorSettingsPage.tsx` | 更新 Provider 凭据、模型和请求端点/Base URL，包括 Meshy Base URL。 |

直接顺序为：创意展示 → 风格图 → 3D 概念图/模型 → 通过 Meshy 和耗材颜色匹配进行白色或 1–8 色校准 → 最终颜色校准 3MF → Meshy + DeepSeek 评分/洞察且不提供建议 → 订单任务提交。

## UI 契约

- 产品 UI 没有付费确认门或问题确认门。计费 Provider smoke 运行是需要在执行时明确人工批准的运维调用，而不是 UI 门。
- 在 root 切片和原生排队前，任务状态必须保留风格/模型预览。模型 3MF 绝不是直接打印任务；root 附加通过验证的 `.gcode.3mf` 后才能原生交接。
- 认证预览使用受控的 Bearer Blob fetch。不要暴露 Provider 临时 URL，也不要把受保护产物路由直接赋给 `<img src>`。
- BCA 路由必须保持在 `components/Layout.tsx` 和 Bambuddy 授权/API 契约内。
- Creator 配置属于敏感数据：Provider 端点和凭据不得泄漏到任务记录、客户端日志或预览。

## 相关文档

- [English frontend guide](README.md)
- [中文 README](../README.md)
- [架构说明](../BCA_ARCHITECTURE.zh-CN.md)
- [部署指南](../DEPLOYMENT_BCA.zh-CN.md)
