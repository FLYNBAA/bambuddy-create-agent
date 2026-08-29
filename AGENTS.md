# BCA — Agent Coding and Technical Guide

This file is the required entry point for all coding work in `bambuddy-create-agent`. Read it before modifying backend, frontend, provider, queue, storage, configuration, deployment, or tests.

## 1. Product Boundary

BCA is a Bambuddy-centered, self-hosted 3D-creation and printing-management backend.

```text
Creative conversation / optional reference image
  → brief extraction and clarification
  → explicit image payment confirmation
  → four serial concept-image requests
  → persisted image selection
  → explicit 3D payment confirmation
  → persisted GLB
  → Meshy multi-color model 3MF
  → geometry-white OR Bambuddy-inventory color calibration
  → BCA task list
  → root supplies sliced .gcode.3mf
  → Bambuddy LibraryFile
  → Bambuddy PrintQueueItem
  → Bambuddy FTPS + MQTT project_file dispatch
```

Bambuddy remains authoritative for:

- printer discovery, connection, state and aliases (`Printer.name`);
- AMS, nozzle, material and queue matching;
- Library files, slicing, print queue, FTPS, MQTT and printer lifecycle;
- users, authentication, API keys, WebSocket, static SPA serving and deployment;
- camera, webhook, API key and native printer-control routes.

The embedded creator owns only creative sessions and artifacts. Do not create a second printer state machine, queue, auth system, API-key system, file store, static app, or standalone FastAPI app.

## 2. Non-negotiable Security Rules

- Never read, copy, display, log, commit, serialize, document, or echo real secret values from `.env`, `.env.local`, conversation text, provider responses, screenshots, or process environment.
- Provider credentials are deployment-only environment variables or Docker/Kubernetes Secrets. The UI may report `configured: true|false`; it must never expose the value.
- Any credentials supplied in a chat or issue are treated as exposed. Operators must rotate them before production use.
- Do not put a provider API key, cloud SecretId/SecretKey, webhook secret, signed URL, absolute artifact path or supplier job ID in API responses, errors, documents, tests or frontend state.
- Meshy webhook authenticity is not assumed. Do not add a webhook endpoint or accept webhook state transitions until a verified Meshy signature contract and replay policy exist.
- Provider paid POSTs are never automatically retried. A network interruption may already have billed a request.
- No paid image, 3D, repair, or multi-color call may be made for routine tests. The explicit smoke runner is the only approved manual entry point and requires `--confirm-paid`.

## 3. Runtime and Deployment Model

- Python 3.11+; the local project `.venv` is the standard development environment.
- React + Vite frontend builds into `static/`; FastAPI serves the SPA and `/api/v1` from the same origin.
- BCA inherits Bambuddy’s single-process coordination. Do not run multiple Uvicorn workers or multiple BCA replicas while `ThreeDPrintAgent` uses process-local locks and task maps.
- Linux host networking is Bambuddy’s default because discovery, Virtual Printer, camera and printer LAN transport require it. Bridge mode requires the documented explicit ports and manual printer IP configuration.
- Docker is supported by the inherited multi-stage `Dockerfile`; BCA dependencies are in `requirements.txt`.

Use these commands locally:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
npm --prefix .\frontend ci
npm --prefix .\frontend run build
$env:DATA_DIR = "$PWD\data"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Do not use source-project `.env` files as an input to BCA. Inject rotated production credentials directly into the BCA deployment environment.

Windows Docker Desktop smoke uses the bridge override, not Linux host networking:

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml build
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d
curl http://127.0.0.1:8012/health
curl http://127.0.0.1:8012/api/v1/creator/config
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml down -v
```

The override uses `network_mode: !reset null`; do not replace it with an empty string, which creates Docker's `none` network and prevents host port publishing. Bridge mode requires manual printer IP setup.

## 4. Backend Structure

```text
backend/app/
├─ main.py                              FastAPI composition root and lifespan
├─ core/
│  ├─ config.py                         Bambuddy paths/settings
│  ├─ database.py                       async DB, migrations and init_db
│  ├─ permissions.py                    native permission enum
│  ├─ tasks.py                          native background task helper
│  └─ websocket.py                      native WebSocket manager
├─ api/routes/
│  ├─ creator.py                        /api/v1/creator
│  ├─ bca_tasks.py                      /api/v1/bca-tasks
│  ├─ library.py                        native LibraryFile persistence/slicing
│  ├─ print_queue.py                    native queue API and dispatch contract
│  ├─ printers.py                       printer state, aliases and native control
│  ├─ inventory.py                      manual spool inventory
│  └─ api_keys.py / webhook.py          native external integration surface
├─ models/
│  ├─ bca_task.py                       BCA task table
│  ├─ spool.py                          manual active spool inventory
│  ├─ printer.py                        name = persistent operator alias
│  └─ print_queue.py                    native queue item
├─ services/
│  ├─ creator_integration.py            BCA composition, config persistence, WS events
│  ├─ creator_inventory.py              Bambuddy Spool → creator color candidate adapter
│  ├─ print_scheduler.py                native queue dispatch authority
│  ├─ bambu_ftp.py                      native FTPS transport
│  └─ bambu_mqtt.py                     native MQTT project_file authority
└─ three_d_agent/
   ├─ contracts.py                      creator models, states and protocols
   ├─ service.py                        creator orchestration and paid gates
   ├─ conversation.py                   LangGraph creator command planner
   ├─ graph.py                          free brief preparation graph
   ├─ prompts.py                        print-aware prompt builder
   ├─ calibration.py                    safe 3MF color/geometry transforms
   ├─ storage.py                        SQLite sessions and validated artifacts
   ├─ factory.py                        provider composition
   └─ providers/                        DeepSeek, image, Hunyuan and Meshy adapters
```

## 5. Creator State Machine and Gates

Main session state:

```text
needs_input
  → awaiting_image_confirmation
  → queued_image
  → generating_images
  → awaiting_image_selection
  → awaiting_3d_confirmation
  → queued_3d
  → generating_3d
  → completed | failed
```

Post-model subworkflows:

```text
print_analysis:    not_started → queued → running → succeeded | failed
print_file:        not_started → queued → running → succeeded | failed
color_calibration: not_started → queued → running → succeeded | failed
geometry_status:   not_started → running → succeeded | failed
```

Rules:

1. `prepare()` is free and may only enrich the brief, ask questions and build a prompt.
2. Image generation requires `awaiting_image_confirmation`, a complete brief and `image_prompt`.
3. Image calls remain four serial `n=1` paid requests. Each successful image is saved and surfaced immediately. Selection remains blocked until all four persisted paths exist.
4. 3D generation requires a selected persisted image and `awaiting_3d_confirmation`.
5. The BCA UI and API do not expose Meshy topology repair. Do not re-add it without a product decision and an explicit paid confirmation design.
6. Multi-color 3MF is limited to `1..8` colors in BCA.
7. Every provider result must be downloaded, validated and stored before the public API exposes it.
8. Main generation cancellation/failure produces main `failed`; post-model workflow failure must not discard a completed GLB.
9. A restart never bypasses a paid confirmation. Restarting `brief`, `images`, or `model` must clear every downstream GLB/print/calibration/geometry path and nested status before the new boundary is exposed; stale artifacts must never remain downloadable or task-eligible.
10. If print analysis is not `healthy`, multi-color generation additionally requires an explicit issue acknowledgment. The UI checkbox and chat wording must state that the reported issues are understood; never silently set `acknowledge_issues=True`.

## 6. Global Agent Conversation

`three_d_agent/conversation.py` compiles a LangGraph `StateGraph` that asks DeepSeek structured output to choose one constrained action:

```text
prepare | confirm_images | select_image | confirm_3d | analyze
| generate_print_file | geometry | calibrate | restart_question
```

- Conversation turns persist in `SessionSnapshot.conversation`; retain only the latest bounded history.
- The graph chooses a tool action; `creator.py` performs the actual service call.
- Paid actions still require an explicit user message containing Chinese `确认` and a structured `explicit_confirmation=true` result. Service gate checks remain authoritative.
- The reference-image flow uses the regular preparation endpoint because it requires multipart upload; do not silently discard a reference image to route it through chat.
- Do not move paid provider calls into LangGraph nodes. Service state, confirmation gates, idempotency and cancellation are outside the planning graph.

## 7. Artifact and 3MF Contract

Creator model 3MF validation only proves that the ZIP includes:

```text
[Content_Types].xml
3D/*.model
```

It does **not** prove a file is printer-ready.

A task may enter Bambuddy’s native queue only after root attaches a sliced 3MF containing:

```text
Metadata/plate_N.gcode
Metadata/slice_info.config
```

`bca_tasks.py` validates both before creating the LibraryFile. The sliced filename must end in `.gcode.3mf`. Both model and sliced BCA uploads are capped at 100 MB and use bounded 3MF ZIP member, compression-ratio and uncompressed-size validation. Never queue a model-only 3MF.

### Calibration modes

- **Geometry mode**: `geometry_only_3mf()` normalizes supported color metadata to white while retaining valid geometry/property references. It is for a single white-material workflow, not a destructive geometry conversion.
- **Multi-color mode**: source colors are mapped by DeepSeek to actual Bambuddy active manual Spools. `creator_inventory.py` reads unarchived `Spool` rows with valid RGBA, material, brand and color name. Missing/invalid color data is excluded; no fallback color is invented.

The original model 3MF is never overwritten. Geometry and calibrated copies are separate artifacts.

For Meshy `public_url` model input, the provider receives only the controlled capability route `/api/v1/creator/sessions/{session_id}/model.glb`. It is not returned in public snapshots; it exists solely so Meshy can fetch the GLB without a browser credential.

## 8. BCA Task Contract

`BCATask` state:

```text
awaiting_slice
  → attach validated .gcode.3mf → ready_for_queue
  → root chooses printer → queued
```

Task API:

```text
GET    /api/v1/bca-tasks
POST   /api/v1/bca-tasks
GET    /api/v1/bca-tasks/{id}/source
POST   /api/v1/bca-tasks/{id}/sliced
POST   /api/v1/bca-tasks/{id}/queue
DELETE /api/v1/bca-tasks/{id}
```

Queue handoff uses native `add_to_queue()` and sets `manual_start=True`. Native Bambuddy controls own all subsequent start, cancel, AMS, material, FTPS, MQTT, print status and archive behavior.

Task deletion permanently removes the BCA task record and its BCA-owned source copy. It must not delete the native LibraryFile or an already-created Bambuddy PrintQueueItem.

## 9. Configuration and External APIs

Creator config endpoint:

```text
GET /api/v1/creator/config
PUT /api/v1/creator/config
```

Persisted, non-secret values:

```text
bca_creator_deepseek_base_url
bca_creator_deepseek_model
bca_creator_image_base_url
bca_creator_image_model
bca_creator_image_quality
bca_creator_meshy_model_input_mode
bca_creator_app_public_base_url
```

They are restored during FastAPI lifespan startup. Provider secrets remain environment-only.

Native Bambuddy API keys, webhook routes, camera routes and printer-control routes remain the external integration mechanism. Add BCA-specific external routes under `/api/v1/creator` or `/api/v1/bca-tasks`, then apply existing Bambuddy permission dependencies. Do not create an unauthenticated BCA API surface.

## 10. WebSocket Contract

Creator background stages publish this native WebSocket event:

```json
{
  "type": "bca_creator_session",
  "session_id": "...",
  "stage": "images|model|analysis|print-file|geometry|calibration",
  "event": "running|updated|failed",
  "status": "...",
  "image_count": 0,
  "geometry_status": "...",
  "print_file_status": "...",
  "color_calibration_status": "..."
}
```

The React `useWebSocket` hook dispatches `bca:creator-session`; `CreatorPage` refreshes only when the event session ID matches the active session. The persistent session snapshot remains authoritative. Current BCA is root-only, so WebSocket fan-out is local-root safe. Add per-user session ownership before enabling multi-user BCA.

## 11. Database Migration Rules

- `init_db()` imports `bca_task` so `Base.metadata.create_all()` creates BCA tables for fresh databases.
- `run_migrations()` contains an idempotent migration for legacy `bca_tasks.print_queue_item_id` and its index.
- Any new BCA persistent model/column requires both fresh-schema coverage and an idempotent upgrade path for SQLite and PostgreSQL.
- Never change a persistent field name or state enum without a migration and a snapshot compatibility test.

## 12. Frontend Structure

```text
frontend/src/
├─ pages/CreatorPage.tsx             creator session/chat/canvas
├─ pages/TaskListPage.tsx            task intake, slice upload, printer picker
├─ pages/CreatorSettingsPage.tsx     non-secret provider configuration
├─ hooks/useWebSocket.ts             BCA event dispatch integration
├─ components/Layout.tsx             sidebar entries
├─ api/client.ts                     native auth-token access
└─ i18n/locales/*                    every sidebar key in every locale
```

Routes:

```text
/creator
/tasks
/creator/settings
```

UI requirements:

- Creator: left session list, narrow middle chat/control, right workflow canvas.
- Task list: creation time order, username/root display, source download, sliced-file attachment, printer `name (model)` picker and delete action.
- Queue and printer pages remain native Bambuddy pages.
- Any new nav key must be added to every locale or `check:i18n` will fail.
- UI changes require `npm run build` and browser verification of the actual surface.

## 13. Verification Commands

```powershell
# Python syntax
.\.venv\Scripts\python.exe -m py_compile <changed python files>

# Focused BCA tests
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest `
  backend\tests\unit\test_bca_geometry.py `
  backend\tests\unit\test_bca_task_validation.py `
  backend\tests\unit\test_bca_incremental_images.py `
  backend\tests\unit\test_bca_creator_inventory.py `
  backend\tests\unit\test_bca_ws_events.py -q

# Lint changed BCA files
.\.venv\Scripts\ruff.exe check <changed files>

# Frontend type check + production build
npm --prefix .\frontend run build
```

Manual, non-billed provider readiness check:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_provider_smoke.py --base-url http://127.0.0.1:8000
```

Paid image smoke, only after explicit operator approval and deployment-secret injection:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_provider_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --confirm-paid
```

The runner stops after the four-image request is accepted. It does not submit Hunyuan or Meshy work.


Full paid-chain smoke, only after explicit approval of image, Hunyuan, Meshy multi-color and DeepSeek calibration charges:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_full_paid_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --confirm-paid `
  --seed-calibration-spool
```

The initial full-chain command intentionally stops before Meshy multi-color generation when analysis is not `healthy`; it cannot pre-approve unseen defects. `--seed-calibration-spool` creates then removes a local active PLA test spool so calibration has an inventory candidate after a healthy analysis. The runner also creates a task from the calibrated 3MF; the resulting task remains intentionally unsliced and cannot be queued until a slicer produces a validated `.gcode.3mf`.

If a full run stops after non-healthy analysis, do **not** repeat the paid image or 3D stages. Review the existing session's report, then resume only Meshy print generation:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_full_paid_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --session-id <existing-session-id> `
  --confirm-paid `
  --acknowledge-print-issues `
  --seed-calibration-spool
```

## 14. Completion Checklist for a Future Coding Agent

Before reporting work complete:

- [ ] All impacted BCA routes, states, frontend views and tests are updated.
- [ ] No real secret is in the working tree, output, test fixture or documentation.
- [ ] No paid call was made unless the user explicitly approved that exact stage.
- [ ] Model-only 3MF was never queued without a validated sliced `.gcode.3mf`.
- [ ] All creator artifacts remain downloadable through controlled BCA routes only.
- [ ] Native Bambuddy queue/mapping logic has not been duplicated or bypassed.
- [ ] `ruff`, focused pytest and frontend build pass.
- [ ] New persistent DB state has a migration path.
- [ ] Docker build/start is run on a Docker-capable host after deployment environment secrets are injected.
