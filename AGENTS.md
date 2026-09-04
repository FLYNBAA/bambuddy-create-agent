# BCA — Agent Coding and Technical Guide

This file is the required entry point for all coding work in `bambuddy-create-agent`. Read it before modifying backend, frontend, provider, queue, storage, configuration, deployment, or tests.

[中文](AGENTS.zh-CN.md) | **English**

## 1. Product Boundary

BCA is a Bambuddy-centered, self-hosted 3D-creation and printing-management backend.

```text
Creative input / optional reference image
  → DeepSeek creative completion
  → four serial Image2 style images
  → persisted style-image selection
  → Hunyuan 3D concept GLB
  → Meshy 3MF + white or 1–8-color inventory calibration
  → Meshy + DeepSeek print score/insights (no advice)
  → order task (title, user, customer, phone, address, notes, optional price, previews)
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

## 2. Credential Storage and Paid-Provider Rules

- Provider credentials may be entered, read, returned and hot-reloaded as plaintext through `/api/v1/creator/config` at the user's explicit product decision. They are persisted under `bca_creator_*` Bambuddy settings rows and appear in database backups.
- The Agent Services page and config API are therefore restricted to Bambuddy settings permissions. Do not create an unauthenticated credential route.
- Do not log credentials, include them in ordinary creator session snapshots, send them to third-party clients, or commit a populated `.env` file.
- Any credentials supplied in a chat or issue are treated as exposed. Operators must rotate them before production use.
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

Environment variables supply initial Provider values, but Agent Services may replace and persist plaintext Provider credentials at runtime. BCA still does not read source-project `.env` or `.env.local` files.

Windows Docker Desktop smoke uses the bridge override, not Linux host networking:

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml build
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d
curl http://127.0.0.1:8012/health
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml down
```

Use `down -v` only for an explicitly disposable smoke stack; it deletes named data volumes.

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
   ├─ service.py                        direct creator workflow orchestration
   ├─ graph.py                          DeepSeek brief preparation graph
   ├─ prompts.py                        print-aware prompt builder
   ├─ calibration.py                    safe 3MF color/geometry transforms
   ├─ storage.py                        SQLite sessions and validated artifacts
   ├─ factory.py                        provider composition
   └─ providers/                        DeepSeek, image, Hunyuan and Meshy adapters
```

## 5. Creator State Machine

The product surface is a direct sequence of workflow cards:

```text
creative input → prepared brief
  → image generation → image selection
  → 3D concept generation
  → print calibration (white | multicolor 1..8)
  → print analysis
  → order task submission
```

Rules:

1. `prepare()` always auto-completes: it enriches the brief, builds the Image2 prompt, and returns final prompts. There is no clarification or type-choice path; the compatibility `questions` field stays empty and `image_prompt_ready` is true for accepted input.
2. Image generation requires a complete brief and prompt. It runs exactly four serial `n=1` calls; no paid Provider POST is retried automatically.
3. Each completed image is persisted and exposed immediately. A persisted image selection is required for 3D concept generation.
4. Hunyuan output is downloaded, validated, and persisted before the GLB preview route is exposed.
5. Print calibration runs after GLB completion. White mode requests one logical color and normalizes the final 3MF to white. Multicolor accepts `1..8`, runs Meshy conversion, then DeepSeek matching against active Bambuddy inventory.
6. Print analysis is exposed only after final calibration; Meshy analyzes the persisted GLB and DeepSeek turns those metrics into a score and factual insights. It must not emit recommendations.
- Creator persists source-language prompt fields alongside `presentation_en` / `presentation_zh`. Direct `brief/prepare` returns the final prompt bundle; it has no clarification or presentation-stream gate, and `questions` remains empty. UI surfaces may show that returned bundle according to their API contract.
- Creator calibration consumes only active `spool` rows with `archived_at IS NULL`, non-empty `material`, and valid RGB/RGBA. It does not use `color_catalog` as a calibration inventory source. A successful multicolor calibration requires non-empty `assignments` plus the final calibrated artifact.
7. The UI and API contain no paid-confirmation or issue-acknowledgement gates. Billed smoke runs still require explicit operator approval at the point of execution; automatic retries remain prohibited.
8. Every redo clears the selected stage and all downstream paths, states, pending Provider URLs, and task eligibility. Stale artifacts must never remain downloadable.
9. Main and subworkflow cancellation/failure persists a terminal failed state; no session may remain running after process recovery.

## 6. Direct Workflow API

The frontend uses the typed Creator endpoints directly:

```text
POST /sessions/{id}/prepare
POST /sessions/{id}/images/generate
POST /sessions/{id}/model/generate
POST /sessions/{id}/print/calibrate
POST /sessions/{id}/print/analyze
POST /sessions/{id}/task
```

- The Creator page does not expose or depend on a global Agent conversation.
- Reference images use the multipart preparation endpoint and are retained with the session.
- Provider calls remain in the service layer, outside LangGraph nodes. Service state, persistence, cancellation, artifact validation, and the no-retry boundary remain authoritative.
- Background stage events are persisted first; WebSocket delivery is advisory and polling remains the recovery path.

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

Both model and sliced BCA uploads share the 512 MiB calibration package limit and use bounded 3MF ZIP member, duplicate-member, compression-ratio and uncompressed-size validation. Never queue a model-only 3MF.

### Calibration modes

- **White mode**: Meshy generates a one-color model 3MF and `geometry_only_3mf()` normalizes every supported palette entry to opaque white while preserving valid geometry/property references.
- **Multicolor mode**: Meshy generates a `1..8`-color model 3MF, then DeepSeek maps every source color to an active Bambuddy manual spool. `creator_inventory.py` excludes archived spools and rows without valid RGBA/material data; no fallback color is invented.

The final calibrated 3MF is a separate persisted artifact and the only creator output eligible for order submission. The intermediate Meshy 3MF is never task-eligible.
Multicolor and calibration artifacts embed a best-effort colored 512×512 `Metadata/plate_1.png` snapshot. Snapshot generation runs once per artifact, off the async event loop, bounded to 500k faces, and fails open (a missing or unrenderable snapshot never fails the artifact). The `X-BCA-Color-Snapshot` header reports `created|present|skipped` for multicolor and `replaced|skipped` for calibration.

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
GET    /api/v1/bca-tasks/{id}/snapshot
POST   /api/v1/bca-tasks/{id}/sliced
POST   /api/v1/bca-tasks/{id}/queue
DELETE /api/v1/bca-tasks/{id}
```

The task list response keeps `source_3mf_url` for downloading the full model 3MF and adds `source_3mf_snapshot_url` for `GET /api/v1/bca-tasks/{id}/snapshot`, which returns only the embedded `Metadata/plate_1.png` color snapshot and returns 404 when the 3MF has none. The task UI displays only that snapshot; it never renders full 3MF geometry.

Direct `POST /api/v1/bca-tasks` accepts a model `.3mf` and rejects GLB and sliced `.gcode.3mf` files. Optional title, customer name, phone, address, notes, price, and reference image fields are accepted; a direct file without an embedded snapshot may have no task preview rather than a rendered one.

Queue handoff uses native `add_to_queue()` and sets `manual_start=True`. Native Bambuddy controls own all subsequent start, cancel, AMS, material, FTPS, MQTT, print status and archive behavior.

Task deletion permanently removes the BCA task record and its BCA-owned source copy. It must not delete the native LibraryFile or an already-created Bambuddy PrintQueueItem.

## 9. Configuration and External APIs

Creator config endpoint:

```text
GET /api/v1/creator/config
PUT /api/v1/creator/config
```

Persisted plaintext Creator configuration includes Provider credentials and runtime values:

```text
bca_creator_deepseek_api_key
bca_creator_deepseek_base_url
bca_creator_deepseek_model
bca_creator_image_api_key
bca_creator_image_base_url
bca_creator_image_model
bca_creator_image_quality
bca_creator_tencent_secret_id
bca_creator_tencent_secret_key
bca_creator_tencent_region
bca_creator_meshy_api_key
bca_creator_meshy_model_input_mode
bca_creator_app_public_base_url
```

They are restored during FastAPI lifespan startup. Both plaintext `GET /api/v1/creator/config` and hot-reloading `PUT` require Bambuddy `SETTINGS_UPDATE`; read-only status/API-key scopes cannot retrieve Provider secrets. Database backups therefore contain these values.

Native Bambuddy API keys, webhook routes, camera routes and printer-control routes remain the external integration mechanism. Add BCA-specific external routes under `/api/v1/creator` or `/api/v1/bca-tasks`, then apply existing Bambuddy permission dependencies. Do not create an unauthenticated BCA API surface.

## 10. WebSocket Contract

Creator background stages publish this native WebSocket event:

```json
{
  "type": "bca_creator_session",
  "session_id": "...",
  "stage": "images|model|analysis|calibration",
  "event": "running|updated|failed",
  "status": "...",
  "image_count": 0,
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
├─ pages/CreatorPage.tsx             progressive Creator workflow cards
├─ pages/TaskListPage.tsx            task intake, slice upload, printer picker
├─ pages/CreatorSettingsPage.tsx     plaintext Provider configuration and hot reload
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
- Task list: creation time order, username/root display, embedded color-snapshot preview only (never rendered 3MF geometry), source 3MF download, sliced-file attachment, printer `name (model)` picker and delete action.
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

Paid image smoke, only after explicit operator approval and configured Provider credentials (from deployment environment or Agent Services):

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_provider_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --confirm-paid
```

The runner stops after the four-image request is accepted. It does not submit Hunyuan or Meshy work.


Full paid-chain smoke, only after explicit approval of Image2, Hunyuan, Meshy calibration, DeepSeek analysis/title, and their applicable charges:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_full_paid_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --confirm-paid `
  --seed-calibration-spool
```

The runner follows the direct card contract: prepare, four style images, selected-image 3D concept, white or multicolor calibration, Meshy + DeepSeek analysis, and order submission. `--seed-calibration-spool` selects the multicolor path and creates then removes one local PLA test spool. Without it, the runner uses white mode. The created task remains intentionally unsliced and cannot enter the native queue until root supplies a validated `.gcode.3mf`.

If a run stops after the GLB is persisted, do **not** repeat Image2 or Hunyuan. Resume calibration, analysis, and order submission for that same session:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_full_paid_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --session-id <existing-session-id> `
  --confirm-paid `
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
- [ ] Docker build/start is run on a Docker-capable host after deployment configuration or Agent Services plaintext credentials are supplied.
- [ ] New persistent DB state has a migration path.
