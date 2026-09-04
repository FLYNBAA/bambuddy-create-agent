# Bambuddy Frontend

[中文](README.zh-CN.md) | **English**

The React + TypeScript + Vite frontend is built into repository-level `static/` and served by the Bambuddy application. BCA remains embedded in that application; do not create a second application shell, independent production frontend, or standalone agent-chat surface.

## BCA surfaces

| Route | Component | Current responsibility |
|---|---|---|
| `/creator` | `pages/CreatorPage.tsx` | Independent API test bench for source-language brief expansion, structured prompt inspection, Image2, model generation, calibration, analysis, and artifact preview. GLBs preview interactively; 3MFs preview only through their embedded color snapshot. |
| `/tasks` | `pages/TaskListPage.tsx` | Preserve title/user/customer/phone/address/notes, an optional price, a style image, and an embedded color 3MF snapshot; accept root slicing, select a printer, and submit to Bambuddy's native queue. The list previews only the embedded color snapshot from `source_3mf_snapshot_url`; `source_3mf_url` keeps the full 3MF download. |
| `/creator/settings` | `pages/CreatorSettingsPage.tsx` | Update provider credentials, models, and request endpoint/Base URLs, including the Meshy base URL. |

The direct order is brief expansion → Image2 → 3D concept image/model → white or 1–8-color calibration using Meshy and material color matching → final color-calibrated 3MF → Meshy + DeepSeek score/insights without advice → order task submission.

Brief expansion preserves the caller's source language and always auto-completes: once `subject`, `style`, and `product_type` are populated, it returns `positive_prompt`, `negative_prompt`, `print_constraints`, and the composed `image2_prompt`; there is no clarification path, and the compatibility `questions` field is always empty. The bench makes that completed Image2 text the next-tab input. No presentation streaming or bilingual display shim gates the direct API surface. Model previews preserve source color/materials; a visual fallback colors untextured near-white GLBs without altering downloaded artifacts. Calibration and multicolor 3MFs embed a best-effort colored 512×512 `Metadata/plate_1.png` snapshot, and 3MF artifacts are previewed through that snapshot rather than a WebGL 3MF renderer.


## UI contracts

- The product UI has no paid confirmation or issue-acknowledgement gates. A billed-provider smoke run is an operational invocation requiring explicit human approval at execution time, not a UI gate.
- Keep style images and embedded color 3MF snapshots available in task state until root slicing and native queueing. A model 3MF is never a direct printer job; root attaches a validated `.gcode.3mf` before native handoff.
- Authenticated previews use a controlled Bearer-authenticated Blob fetch. Do not expose provider temporary URLs or assign protected artifact routes directly to `<img src>`.
- Keep BCA routes inside `components/Layout.tsx` and use Bambuddy’s authorization model and API contracts.
- Keep Creator configuration sensitive: provider endpoints and credentials must not leak into task records, client logs, or previews.

## References

- [中文前端说明](README.zh-CN.md)
- [English README](../README.en.md)
- [Architecture](../BCA_ARCHITECTURE.md)
- [Deployment](../DEPLOYMENT_BCA.md)
