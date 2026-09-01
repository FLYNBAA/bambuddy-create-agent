# Bambuddy Create Agent (BCA)

[中文](README.md) | **English**

BCA is a Bambuddy-based extension that embeds AI 3D creation, model calibration, and task handoff into Bambuddy's existing printer, inventory, queue, permission, and deployment system. It is not a standalone create-agent service.

## Use cases

- Run a self-hosted creator and print-management backend on local Windows, LAN Linux, or public Linux infrastructure.
- Generate print-oriented models through chat or direct workflow cards.
- Keep Bambuddy native printer management, print queue, inventory, API keys, webhooks, cameras, and permissions.
- Let root attach a sliced file after a model is complete, then safely dispatch it to a chosen printer.

## Workflow

```text
Creative text / optional reference image
  → DeepSeek enriches subject, style, and product type; asks for missing data
  → explicit confirmation for four concept images
  → GPT Image serially creates and persists candidates
  → choose a candidate and explicitly confirm 3D generation
  → Hunyuan generates and persists GLB
  → Meshy free print analysis
  → explicit confirmation for model 3MF (1–8 color slots)
  → geometry-white or Bambuddy-inventory color calibration
  → BCA task list
  → root uploads sliced .gcode.3mf
  → Bambuddy LibraryFile / PrintQueueItem
  → native FTPS + MQTT dispatch
```

## Non-negotiable rules

1. Image, 3D, and Meshy multi-color operations have separate payment gates; billed POSTs are never auto-retried.
2. Concept images are exactly four serial `n=1` requests; every persisted image becomes visible immediately.
3. Meshy topology repair is not exposed through the BCA UI or API.
4. A non-`healthy` analysis requires a separate acknowledgement of its findings before multi-color generation.
5. Restarting the brief, image, or model stage invalidates downstream artifacts and pending provider URLs. Stale output cannot be downloaded or handed off.
6. Geometry-white and calibrated multi-color 3MFs are separate artifacts; the original multi-color 3MF is retained.
7. A BCA model 3MF is never sent directly to a printer. Root must upload a validated sliced `.gcode.3mf` before native queue handoff.

A valid sliced package contains both:

```text
Metadata/plate_N.gcode
Metadata/slice_info.config
```

## Administration UI

| Page | Route | Purpose |
|---|---|---|
| 3D Creator | `/creator` | Session list, Agent chat, four-stage canvas, candidate selection, artifact downloads, calibration, and task handoff. |
| BCA Tasks | `/tasks` | Model download, sliced-file attachment, `name (model)` printer selection, native queue handoff, and permanent deletion. |
| Agent Services | `/creator/settings` | Enter, read, persist, and hot-reload every Provider parameter and plaintext credential. |
| Native Bambuddy pages | Printers, inventory, queue, and others | Preserve native behavior and permission semantics. |

When authentication is enabled, candidate previews are loaded through Bearer-authenticated Blob requests. Do not replace this with raw controlled artifact URLs in `<img src>`.

## Local development on Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
npm --prefix .\frontend ci
npm --prefix .\frontend run build
$env:DATA_DIR = "$PWD\data"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. On first use, create a local administrator and configure authentication according to your security policy.

## Configuration and plaintext credentials

- Agent Services directly enters, reads, persists, and hot-reloads all DeepSeek, image-provider, Tencent Hunyuan, and Meshy credentials.
- `GET /api/v1/creator/config` returns plaintext credentials to callers with `SETTINGS_READ`; `PUT` requires `SETTINGS_UPDATE` and immediately rebuilds Agent Providers.
- Plaintext values are stored as `bca_creator_*` Bambuddy database settings, so database readers and database backups can read them.
- BCA does not read source-project `.env` or `.env.local`. Environment variables supply only first-start values and the web configuration can replace them.
- Do not put credentials in ordinary creator sessions, task records, source code, public documentation, or uncontrolled clients.

Provider credentials available in Agent Services:

```text
DEEPSEEK_API_KEY
IMAGE_API_KEY
TENCENT_SECRET_ID
TENCENT_SECRET_KEY
MESHY_API_KEY
```

With `MESHY_MODEL_INPUT_MODE=public_url`, `BCA_PUBLIC_BASE_URL` must be publicly reachable over HTTPS. Meshy receives only this controlled GLB capability route:

```text
/api/v1/creator/sessions/{session_id}/model.glb
```

## Linux Docker Compose development

`docker-compose.dev.yml` separates the backend and Vite frontend into hot-reloading services and bind-mounts the source tree. It does not use host networking or expose Virtual Printer ports; do not use it for printer-LAN integration or production deployments.

Optionally create a Provider environment file used only by the development backend before its first start:

```bash
cp .env.bca.example .env.bca
chmod 600 .env.bca
# Edit .env.bca: remove unused <inject-secret> placeholders and supply real values.
```

Compose injects `.env.bca` only into the `backend` service; the frontend container never receives Provider credentials, and the file is excluded from Git and Docker build contexts. Set `BCA_PUBLIC_BASE_URL` to a publicly reachable HTTPS origin only with `MESHY_MODEL_INPUT_MODE=public_url`; local development should retain `data_uri` or remove that variable.

```bash
docker compose -f docker-compose.dev.yml up --build
```

Develop at `http://127.0.0.1:5173`; Vite proxies API and WebSocket traffic through `BACKEND_HOST=backend` and `BACKEND_PORT=8000`. Native development retains `localhost:8000` when neither variable is set. The backend health endpoint is `http://127.0.0.1:8000/health`. Ports bind to loopback by default. To deliberately allow LAN access, set `BCA_FRONTEND_BIND=0.0.0.0` and/or `BCA_BACKEND_BIND=0.0.0.0` before starting.

```bash
docker compose -f docker-compose.dev.yml down
```

`down -v` deletes this development stack's SQLite, log, and frontend-dependency volumes; use it only when intentionally resetting development data.

## Docker and networking

Recommended Linux deployment:

```bash
docker compose up -d --build
```

Windows Docker Desktop:

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d --build
curl http://127.0.0.1:8012/health
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml down
```

Use `down` for ordinary stops; do not use `down -v` for a deployment with data because it removes named data volumes. Linux defaults to host networking for discovery, Virtual Printer, cameras, and printer LAN protocols. The Windows bridge override uses `network_mode: !reset null`; add printers by LAN IP and map extra ports for SSDP or the full passive FTP range.

## Backup and restore

Back up and restore these as **one recovery point**:

1. `DATA_DIR`: BCA creator sessions/artifacts in `bca-agent`, task source files in `bca-tasks`, archives, and Library data.
2. The native Bambuddy database: the SQLite database file plus consistent WAL sidecars, or a complete external PostgreSQL dump.
3. Plaintext Provider configuration: the `bca_creator_*` Bambuddy settings rows and any required first-start deployment environment declarations.

If `DATABASE_URL` targets PostgreSQL, `DATA_DIR` alone is insufficient. `bca_tasks` and persisted `bca_creator_*` settings live in the native Bambuddy database. Restore the database together with its matching `DATA_DIR` snapshot to prevent BCA task rows, LibraryFile rows, queue rows, and creator artifacts from diverging.

## Paid smoke policy

Routine tests must never invoke billed providers. Only run the full smoke runner after approving the exact charges:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_full_paid_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --confirm-paid `
  --seed-calibration-spool
```

If analysis is not `healthy`, the initial chain stops before Meshy. Review the report and resume the same session; never regenerate images or 3D:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_full_paid_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --session-id <existing-session-id> `
  --confirm-paid `
  --acknowledge-print-issues `
  --seed-calibration-spool
```

## Developer verification

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check backend\app backend\tests
npm --prefix .\frontend run lint
npm --prefix .\frontend run test:run
npm --prefix .\frontend run build
```

## Current boundary

BCA currently operates as a single-process application. Session locks, background tasks, and scheduling cannot be made multi-process merely by adding Uvicorn workers. Multi-user ownership isolation, distributed locks, durable queue recovery, object storage, and verified provider webhooks require deliberate future implementation.

## References

- [中文 README](README.md)
- [Architecture](BCA_ARCHITECTURE.md)
- [Deployment](DEPLOYMENT_BCA.md)
- [Engineering contract](AGENTS.md)
- [Documentation audit](DOCUMENTATION_AUDIT.md)
- [Frontend guide](frontend/README.md)
