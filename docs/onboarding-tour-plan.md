# BCA 管理后台引导计划

[English](onboarding-tour-plan.en.md) | **中文**

BCA 面向本地 root 管理后台，首次引导应让用户完成正确且不可跳过的关键路径，而不是自动触发任何付费 Provider。

## 建议顺序

1. **认证与管理员**：完成 Setup，理解 `/creator/settings` 返回和保存 Provider 明文值的权限边界。
2. **打印机**：通过 LAN IP 或原生发现添加打印机；Windows bridge 模式强调手工 IP。
3. **耗材**：添加至少一个活动手动 spool 并确认 RGB、材料、品牌和名称，用于多色校准。
4. **Creator**：新建会话，输入创意或参考图，回答缺失字段。
5. **图像确认**：明确告知四张概念图会收费，只有确认后提交。
6. **3D 确认**：选择候选后，单独确认 GLB 生成。
7. **分析与 3MF**：解释 `healthy` 与 warning/error 的差异；非健康分析需要独立问题确认。
8. **Task 与切片**：说明模型 3MF 不能直接进队列，root 必须上传 `.gcode.3mf`。
9. **原生 Queue**：选择 `名称（型号）` 打印机并提交到 Bambuddy 原生队列。

## 不应在引导中做的事

- 不自动调用付费图像、3D 或 Meshy 多色操作；
- 不把模型 3MF 直接推送打印机；
- 不展示或自动复制 Provider 明文值到普通会话/任务；
- 不把 Tailscale 当成认证替代品。

参见 [中文 README](../README.md) 和 [中文部署指南](../DEPLOYMENT_BCA.zh-CN.md)。
