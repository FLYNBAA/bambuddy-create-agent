# BCA 管理后台引导计划

[English](onboarding-tour-plan.en.md) | **中文**

BCA 面向本地 root 管理后台，首次引导应让用户完成正确且不可跳过的关键路径，而不是自动触发任何付费 Provider。

## 建议顺序

1. **认证与管理员**：完成 Setup，理解 `/creator/settings` 返回和保存 Provider 明文值的权限边界。
2. **打印机**：通过 LAN IP 或原生发现添加打印机；Windows bridge 模式强调手工 IP。
3. **耗材**：添加活动手动 spool 并确认 RGB/RGBA、材料、品牌和名称；说明 Creator 校准读取的是这些 `spool` 行，不是颜色目录。
4. **Creator**：将 `/creator` 作为逐模块测试台。输入任意创意或参考图，说明 brief 会按输入语言自动补全、直接返回最终提示词与恒空的兼容 `questions` 列表，并将 `image2_prompt` 直接带入 Image2；不存在缺字段选择或 presentation 流式门槛。
5. **直接阶段**：说明 Image2、混元、校准和分析由直接卡片启动，不存在重复付费或问题确认门；常规引导不调用计费阶段。
6. **分析与 3MF**：解释无建议的评分/洞察。只有 succeeded、非空 assignments 和最终产物同时存在，才可称为多色校准完成。
7. **Task 与切片**：说明模型 3MF 不能直接进队列，root 必须上传 `.gcode.3mf`。
8. **原生 Queue**：选择 `名称（型号）` 打印机并提交到 Bambuddy 原生队列。

## 不应在引导中做的事

- 不自动调用付费图像、3D 或 Meshy 多色操作；
- 不把模型 3MF 直接推送打印机；
- 不展示或自动复制 Provider 明文值到普通会话/任务；
- 不把 Tailscale 当成认证替代品。

参见 [中文 README](../README.md) 和 [中文部署指南](../DEPLOYMENT_BCA.zh-CN.md)。
