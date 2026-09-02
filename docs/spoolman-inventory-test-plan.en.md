# BCA Filament Inventory and Spoolman Test Plan

[中文](spoolman-inventory-test-plan.md) | **English**

This plan covers BCA multi-color calibration using Bambuddy manual inventory. BCA never falls back to a local nearest-color algorithm: DeepSeek must select existing `inventory_id` values from active candidates.

## Preconditions

- Bambuddy database migration is complete and writable;
- At least one active, unarchived `spool` row exists;
- The row has valid `rgba` and non-empty `material`; `color_catalog` entries alone are not calibration candidates;
- Brand and color name improve matching evidence but are not eligibility requirements;
- Default tests use fake Providers. Real multi-color/image/3D calls need separate approval.

## Calibration candidate rules

| Condition | Expected result |
|---|---|
| Active `spool` with valid RGB/RGBA and non-empty material | Included as a DeepSeek color-matching candidate. |
| Color-catalog-only entry with no matching spool | Excluded. |
| Archived spool | Excluded. |
| Missing/invalid RGBA or empty material | Excluded. |
| No candidates | Calibration subworkflow fails; no final artifact is published. |
| A source model color is uncovered | Calibration fails; no nearest-color fallback. |
| Returned `inventory_id` does not exist | Calibration fails. |
| `succeeded` but assignments empty in multicolor mode | Treat as invalid/incomplete verification; do not claim matching succeeded. |

## BCA end-to-end checks

1. Create a completed creator session and start multi-color calibration with `{ "mode": "multicolor", "max_colors": 1-8 }`.
2. Verify `color_calibration` transitions `queued → running → succeeded|failed`.
3. On success, verify `assignments` is non-empty and every assignment references an eligible active spool.
4. Confirm `calibrated_print_file_download_url` exists and the final calibrated 3MF is independent from the transient Meshy download.
5. On no candidates, incomplete mappings, or Provider errors, confirm no final artifact is published and the completed GLB remains available.
6. Only a successful final calibrated 3MF may enter BCA task through `/sessions/{id}/task`.

## Regression command

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest backend\tests\unit\test_bca_creator_inventory.py backend\tests\unit\test_bca_geometry.py -q
```

See the [English engineering contract](../AGENTS.md) and [Chinese test-plan companion](spoolman-inventory-test-plan.md).
