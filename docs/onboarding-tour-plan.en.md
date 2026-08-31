# BCA Administration Onboarding Plan

[中文](onboarding-tour-plan.md) | **English**

BCA is a local root administration surface. First-run onboarding must establish the correct non-skippable path without automatically invoking billed Providers.

## Recommended sequence

1. **Authentication and administrator**: complete Setup and understand permission boundaries around plaintext Provider values at `/creator/settings`.
2. **Printers**: add printers by LAN IP or native discovery; emphasize manual IP in Windows bridge mode.
3. **Inventory**: add at least one active manual spool with RGB, material, brand, and name for multi-color calibration.
4. **Creator**: create a session and submit an idea or reference image; answer missing fields.
5. **Image confirmation**: clearly explain that four concept images incur charges and submit only after confirmation.
6. **3D confirmation**: after selecting a candidate, independently confirm GLB generation.
7. **Analysis and 3MF**: explain `healthy` versus warning/error; non-healthy analysis requires a separate acknowledgement.
8. **Task and slicing**: explain that model 3MF cannot enter queue directly; root must upload `.gcode.3mf`.
9. **Native queue**: select a `name (model)` printer and submit to Bambuddy's native queue.

## Never do during onboarding

- Never automatically call billed image, 3D, or Meshy multi-color operations.
- Never push a model 3MF directly to a printer.
- Never copy plaintext Provider values into ordinary session/task content.
- Never treat Tailscale as an authentication substitute.

See the [English README](../README.en.md) and [English deployment guide](../DEPLOYMENT_BCA.md).
