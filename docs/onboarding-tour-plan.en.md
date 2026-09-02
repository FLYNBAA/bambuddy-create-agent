# BCA Administration Onboarding Plan

[中文](onboarding-tour-plan.md) | **English**

BCA is a local root administration surface. First-run onboarding must establish the correct non-skippable path without automatically invoking billed Providers.

## Recommended sequence

1. **Authentication and administrator**: complete Setup and understand permission boundaries around plaintext Provider values at `/creator/settings`.
2. **Printers**: add printers by LAN IP or native discovery; emphasize manual IP in Windows bridge mode.
3. **Inventory**: add active manual spools with valid RGB/RGBA, material, brand, and name; explain that Creator calibration reads these `spool` rows, not the color catalog.
4. **Creator**: create a session, submit an idea/reference image, then select every missing brief field. Explain that the bilingual presentation streams fully before the style-image card appears, while Provider-only `image_prompt` is never shown.
5. **Direct stages**: explain that Image2, Hunyuan, calibration, and analysis begin from their direct cards without repeated payment or issue-acknowledgement gates; routine onboarding never invokes billed stages.
6. **Analysis and 3MF**: explain score/insights without advice. A multicolor calibration is complete only with succeeded status, non-empty assignments, and a final artifact.
7. **Task and slicing**: explain that model 3MF cannot enter queue directly; root must upload `.gcode.3mf`.
8. **Native queue**: select a `name (model)` printer and submit to Bambuddy's native queue.

## Never do during onboarding

- Never automatically call billed image, 3D, or Meshy multi-color operations.
- Never push a model 3MF directly to a printer.
- Never copy plaintext Provider values into ordinary session/task content.
- Never treat Tailscale as an authentication substitute.

See the [English README](../README.en.md) and [English deployment guide](../DEPLOYMENT_BCA.md).
