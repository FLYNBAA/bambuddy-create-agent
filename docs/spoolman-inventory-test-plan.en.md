# BCA Filament Inventory and Spoolman Test Plan

[中文](spoolman-inventory-test-plan.md) | **English**

This plan covers BCA multi-color calibration using Bambuddy manual inventory. BCA never falls back to a local nearest-color algorithm: DeepSeek must select existing `inventory_id` values from active candidates.

## Preconditions

- Bambuddy database migration is complete and writable;
- At least one active, unarchived manual spool exists;
- The spool has valid `rgba`, material, brand, and color name;
- BCA Provider configuration has been hot-reloaded at `/creator/settings`;
- Default tests use fake Providers. Real multi-color/image/3D calls need separate approval.

## Calibration candidate rules

| Condition | Expected result |
|---|---|
| Active manual spool with valid RGB | Included as a DeepSeek color-matching candidate. |
| Archived spool | Excluded. |
| Missing or invalid RGBA | Excluded. |
| No candidates | Calibration subworkflow fails and original 3MF remains available. |
| A source model color is uncovered | Calibration fails; no nearest-color fallback. |
| Returned `inventory_id` does not exist | Calibration fails. |

## BCA end-to-end checks

1. Create a completed creator session with an original multi-color 3MF.
2. Run `/print/calibrate`.
3. Verify `color_calibration` transitions `queued → running → succeeded|failed`.
4. On success, confirm `print-calibrated.3mf` is independent and original `print.3mf` remains.
5. On no candidates, incomplete mappings, or Provider errors, confirm the main session remains `completed`.
6. Only successful calibrated 3MF may enter BCA task through `/sessions/{id}/task`.

## Regression command

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest backend\tests\unit\test_bca_creator_inventory.py backend\tests\unit\test_bca_geometry.py -q
```

See the [English engineering contract](../AGENTS.md) and [Chinese test-plan companion](spoolman-inventory-test-plan.md).
