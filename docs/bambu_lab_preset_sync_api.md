# BCA Bambu 预设同步 API

[English](bambu_lab_preset_sync_api.en.md) | **中文**

Bambu 预设同步是 Bambuddy 原生 slicer/耗材能力。BCA 不复制预设系统；BCA task 的最终 `.gcode.3mf` 可由使用这些预设的 slicer 流程生成。

## BCA 集成原则

- Creator 只生成模型 3MF、几何白模或校准多色 3MF。
- root 使用 Bambuddy slicer、Slicer-API sidecar 或桌面 slicer 选择 printer/process/filament preset。
- 最终 `.gcode.3mf` 回传 `/tasks`，BCA 只验证结构并交给原生队列。
- BCA 多色校准耗材候选来自 Bambuddy 活动手动 spool；不由 Bambu Cloud preset 直接决定。

## API 开发规则

- 预设同步路由继续使用原生 Bambuddy auth、API Key 和 URL 安全规则。
- 不要让 Creator Provider/明文 Provider 配置进入 Bambu 预设 API response。
- 修改预设 API 时同步检查 slicer sidecar、Library、Queue 和 BCA task 切片交接。

## 验证

1. 导入或同步目标打印机/工艺/耗材预设。
2. 使用该预设完成 slicer 输出。
3. 验证输出包含 `Metadata/plate_N.gcode` 与 `Metadata/slice_info.config`。
4. 上传至 BCA task 并提交原生队列。

参见 [中文 Slicer-API 文档](../slicer-api/README.md)。
