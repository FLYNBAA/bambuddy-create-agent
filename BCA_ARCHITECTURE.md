# BCA Architecture

## Scope

BCA is a Bambuddy-centered, single-process backend and administration surface. Bambuddy remains the authority for printers, native queue dispatch, library files, API keys, authentication, WebSocket connections, and deployment. The embedded creator owns only creative sessions and model artifacts.

## Boundaries

```text
Creator session
  → persisted GLB
  → Meshy model 3MF
  → geometry-white OR inventory-calibrated 3MF
  → BCA task list
  → root supplies sliced .gcode.3mf
  → Bambuddy LibraryFile
  → Bambuddy PrintQueueItem
  → FTPS + MQTT project_file
```

The creator output is never queued directly. A printable file must contain both `Metadata/plate_N.gcode` and `Metadata/slice_info.config`; BCA validates these before accepting the root-supplied sliced file.

## Backend modules

| Module | Responsibility |
|---|---|
| `backend/app/three_d_agent/` | Isolated creative state machine, provider protocols, artifact validation, color/geometry conversion. |
| `backend/app/services/creator_integration.py` | Bambuddy composition boundary, task lifecycle and safe public snapshot projection. |
| `backend/app/api/routes/creator.py` | Authenticated `/api/v1/creator` control surface. |
| `backend/app/models/bca_task.py` | Persistent root task entries. |
| `backend/app/api/routes/bca_tasks.py` | Task upload, sliced-file validation, and explicit queue submission. |
| Bambuddy `library.py`, `print_queue.py`, `print_scheduler.py` | Existing authoritative slicing, queue, printer mapping and transport workflow. |

## Creator invariants

1. Only explicit image and 3D confirmation gates can invoke paid providers.
2. Four concept images are requested serially as one paid `n=1` operation each; no paid retry is introduced.
3. Each image is persisted and visible immediately after its own response. Authenticated browsers retrieve previews through a Bearer-authenticated Blob URL; raw image routes are not assigned directly to `<img>`.
4. Meshy repair is intentionally not exposed by BCA.
5. Multi-color conversion accepts `1..8` slots only. A non-`healthy` analysis requires a separate explicit issue acknowledgement before its paid request.
6. Geometry mode normalizes all supported 3MF color metadata to white while preserving face/property references and geometry. Cancellation and process-restart recovery leave it in `failed`, never `running`.
7. Multi-color calibration reads Bambuddy's active, non-archived manual spool inventory (`Spool.rgba`) through an async adapter. Spools without valid RGB are excluded; empty eligible inventory fails calibration without a fallback.
8. Only a completed geometry or multi-color calibration artifact may enter `BCATask`.
9. Restarting `brief`, `images`, or `model` clears every downstream path, state, repaired model, and pending Meshy repair/print URL. A same-model `print` restart preserves its pending download URL.
10. Deleting a creator session removes only creator-owned local artifacts. Deleting a task never deletes a LibraryFile or an already-created Bambuddy queue item.

## Task state machine

```text
awaiting_slice
  → root uploads a validated sliced .gcode.3mf → ready_for_queue
  → root chooses printer_id → queued
```

The queue handoff creates an ordinary Bambuddy `PrintQueueItem` with `manual_start=True`. Printer control, cancellation, and final lifecycle remain in Bambuddy's native Queue page.

## HTTP surface

- `/api/v1/creator/*`: authenticated creator sessions, artifact download, calibration artifact-to-task handoff.
- `/api/v1/bca-tasks/*`: root task list, sliced file attachment, fixed-printer queue submission, permanent task removal.

For Meshy `public_url` input only, `/api/v1/creator/sessions/{session_id}/model.glb` is a high-entropy provider capability route. It is not included in creator snapshots; normal artifact downloads remain permission-gated.

These routes use Bambuddy permission dependencies; no create-agent standalone app, unscoped route, direct SQLite mutation, filesystem-path response, or provider URL is exposed.

## Deployment

The existing Bambuddy Dockerfile builds React into `/static` and runs one FastAPI process. BCA adds LangChain/LangGraph/provider dependencies to `requirements.txt`; BCA artifacts are stored under `DATA_DIR/bca-agent`, and BCA task source files under `DATA_DIR/bca-tasks`.

`BCA_PUBLIC_BASE_URL` is the namespaced public origin used only when Meshy public-URL input mode needs a reachable callback path. Secrets remain runtime environment or secret-manager inputs. BCA settings do not load source-project `.env` files; deployment injects provider secrets directly into the process environment.

### Configuration persistence

Non-secret Creator Service values are stored under `bca_creator_*` entries in Bambuddy's existing settings table and restored during FastAPI lifespan startup. API keys remain deployment-only environment/Secret values and are intentionally not persisted in the database. Provider base URLs are LAN-service URL validated before hot reconfiguration; malformed or unsafe values return HTTP `422`.

## Next integration layers

- Add a durable LangGraph checkpoint implementation if the single-process session store is replaced with distributed workers.
- BCA creator stage events are published as `bca_creator_session` WebSocket messages carrying the session ID. The local-root deployment broadcasts to its sole active user; multi-user filtering remains part of the future ownership migration.
- Add migration coverage for existing SQLite/PostgreSQL databases and task ownership/user filtering before multi-user rollout.
