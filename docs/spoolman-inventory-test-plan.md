# BCA 耗材库存与 Spoolman 测试计划

[English](spoolman-inventory-test-plan.en.md) | **中文**

本计划覆盖 BCA 使用 Bambuddy 手动耗材库进行多色校准时的库存边界。BCA 不使用本地最近色回退；DeepSeek 必须在活动耗材候选中选择现存 `inventory_id`。

## 前置条件

- Bambuddy 数据库已迁移并可写；
- 至少创建一个活动、未归档的手动 spool；
- spool 具有有效 `rgba`、材料、品牌与颜色名称；
- BCA Provider 配置已在 `/creator/settings` 热加载；
- 使用 fake Provider 进行默认测试，真实多色/图像/3D 调用必须另行批准。

## 校准候选规则

| 情况 | 预期 |
|---|---|
| 活动手动 spool，合法 RGB | 作为 DeepSeek 颜色匹配候选。 |
| 已归档 spool | 排除。 |
| 缺失或非法 RGBA | 排除。 |
| 候选为空 | 校准子流程失败，原始 3MF 保留。 |
| 模型源色未被覆盖 | 校准失败，不允许最近色回退。 |
| 返回不存在的 inventory_id | 校准失败。 |

## BCA 端到端检查

1. 创建完成的 creator session 并得到原始多色 3MF。
2. 运行 `/print/calibrate`。
3. 验证 `color_calibration` 从 `queued` 到 `running` 再到 `succeeded|failed`。
4. 成功时确认 `print-calibrated.3mf` 是独立产物，原 `print.3mf` 保留。
5. 无候选/不完整映射/Provider 错误时确认主会话仍为 `completed`。
6. 仅成功校准 3MF 才可通过 `/sessions/{id}/task` 进入 BCA task。

## 回归命令

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest backend\tests\unit\test_bca_creator_inventory.py backend\tests\unit\test_bca_geometry.py -q
```

参见 [中文工程契约](../AGENTS.zh-CN.md) 与 [English test-plan companion](spoolman-inventory-test-plan.en.md)。
