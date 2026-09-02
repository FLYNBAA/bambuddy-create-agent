# BCA 耗材库存与 Spoolman 测试计划

[English](spoolman-inventory-test-plan.en.md) | **中文**

本计划覆盖 BCA 使用 Bambuddy 手动耗材库进行多色校准时的库存边界。BCA 不使用本地最近色回退；DeepSeek 必须在活动耗材候选中选择现存 `inventory_id`。

## 前置条件

- Bambuddy 数据库已迁移并可写；
- 至少存在一个活动、未归档的 `spool` 行；
- 该行具有合法 `rgba` 与非空 `material`；仅有 `color_catalog` 条目不构成校准候选；
- 品牌和颜色名称能提升匹配依据，但不是候选资格的必要条件；
- 使用 fake Provider 进行默认测试，真实多色/图像/3D 调用必须另行批准。

## 校准候选规则

| 情况 | 预期 |
|---|---|
| 活动 `spool`，合法 RGB/RGBA 且 material 非空 | 作为 DeepSeek 颜色匹配候选。 |
| 仅有颜色目录、没有对应 spool 的条目 | 排除。 |
| 已归档 spool | 排除。 |
| 缺失/非法 RGBA 或 material 为空 | 排除。 |
| 候选为空 | 校准子流程失败，不发布最终产物。 |
| 模型源色未被覆盖 | 校准失败，不允许最近色回退。 |
| 返回不存在的 inventory_id | 校准失败。 |
| 多色模式 `succeeded` 但 assignments 为空 | 视为不完整核验，不能声称匹配成功。 |

## BCA 端到端检查

1. 创建完成的 creator session，以 `{ "mode": "multicolor", "max_colors": 1-8 }` 启动多色校准。
2. 验证 `color_calibration` 从 `queued` 到 `running` 再到 `succeeded|failed`。
3. 成功时验证 `assignments` 非空，且每条 assignment 引用符合条件的活动 spool。
4. 确认存在 `calibrated_print_file_download_url`，且最终校准 3MF 独立于临时 Meshy 下载。
5. 无候选/不完整映射/Provider 错误时确认不发布最终产物，已完成 GLB 仍可用。
6. 仅成功的最终校准 3MF 才可通过 `/sessions/{id}/task` 进入 BCA task。

## 回归命令

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest backend\tests\unit\test_bca_creator_inventory.py backend\tests\unit\test_bca_geometry.py -q
```

参见 [中文工程契约](../AGENTS.zh-CN.md) 与 [English test-plan companion](spoolman-inventory-test-plan.en.md)。
