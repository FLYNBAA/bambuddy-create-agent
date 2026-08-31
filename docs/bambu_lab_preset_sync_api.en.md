# BCA Bambu Preset Sync API

[中文](bambu_lab_preset_sync_api.md) | **English**

Bambu preset sync is a native Bambuddy slicer/inventory capability. BCA does not duplicate the preset system; BCA task's final `.gcode.3mf` can be produced by a slicer flow using these presets.

## BCA integration principles

- Creator generates only model 3MF, geometry-white, or calibrated multi-color 3MF.
- Root uses Bambuddy slicer, Slicer-API sidecar, or desktop slicer to select printer/process/filament presets.
- The final `.gcode.3mf` returns through `/tasks`; BCA validates structure then hands off to native queue.
- BCA multi-color calibration candidates come from active Bambuddy manual spools, not directly from Bambu Cloud presets.

## API development rules

- Preset-sync routes retain native Bambuddy auth, API-key, and URL-safety rules.
- Do not expose Creator Providers or plaintext Provider configuration through Bambu preset API responses.
- When changing preset APIs, check sidecar, Library, Queue, and BCA task sliced-file handoff.

## Verification

1. Import or sync target printer/process/filament presets.
2. Use the preset to produce slicer output.
3. Verify output contains `Metadata/plate_N.gcode` and `Metadata/slice_info.config`.
4. Attach it to a BCA task and submit to native queue.

See the [English Slicer-API guide](../slicer-api/README.en.md).
