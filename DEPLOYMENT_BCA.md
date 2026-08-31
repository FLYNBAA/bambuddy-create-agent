# BCA Deployment Guide

[中文](DEPLOYMENT_BCA.zh-CN.md) | **English**

This guide is for deployment and operations developers. BCA is embedded in Bambuddy and shares its FastAPI process, database, and static frontend. Do not deploy it as a second standalone create-agent service.

## 1. Prerequisites

| Requirement | Detail |
|---|---|
| Python | Local development uses Python 3.11+ and the repository `.venv`. |
| Node.js | Required only for local frontend builds; Docker handles the frontend in its multi-stage image build. |
| Docker | Use Docker Compose for Linux production or Windows Docker Desktop. |
| Networking | Linux host networking is preferred for discovery, Virtual Printer, camera, and printer LAN protocols. |
| Authentication | Enable Bambuddy authentication and API-key management for public or tailnet access. |
| Database | SQLite supports single-machine use; external PostgreSQL must be included in backup and recovery operations. |

## 2. Local Windows development

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
npm --prefix .\frontend ci
npm --prefix .\frontend run build
$env:DATA_DIR = "$PWD\data"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Complete Setup by creating an administrator or by applying your own authentication policy. Do not use multiple Uvicorn workers: BCA session locks and background stage work are process-local.

## 3. Linux Docker

From the repository root:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f bambuddy
```

The Linux Compose configuration defaults to host networking. It is the recommended model for printer discovery, SSDP, Virtual Printer, cameras, and LAN FTP/MQTT.

At minimum set:

```text
DATA_DIR=/app/data
LOG_DIR=/app/logs
BCA_PUBLIC_BASE_URL=https://bca.example.invalid
```

Provider credentials may be injected as first-start environment values or entered after startup in Agent Services:

```text
DEEPSEEK_API_KEY
IMAGE_API_KEY
TENCENT_SECRET_ID
TENCENT_SECRET_KEY
MESHY_API_KEY
```

BCA does not read source-project `.env` or `.env.local`. `.env.bca.example` is a variable-name and default-value reference; do not commit real credentials.

## 4. Windows Docker Desktop

Docker Desktop cannot use the Linux production `network_mode: host`. Use the repository bridge override:

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml build
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d
curl http://127.0.0.1:8012/health
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml down
```

Use `down` for ordinary stops. `down -v` deletes named data volumes and is only appropriate for an intentionally disposable smoke stack.

The override contains:

```yaml
network_mode: !reset null
ports:
  - "${BCA_DOCKER_PORT:-8012}:8000"
```

Do not replace `network_mode` with an empty string; it creates Docker's `none` network and prevents port publishing.

Bridge-mode limits:

- Add printers by LAN IP; SSDP discovery is unavailable.
- Full Virtual Printer passive FTP and additional camera/proxy capabilities require explicit extra mappings.
- Set `BCA_DOCKER_PORT` if `8012` is already occupied.

## 5. Agent Services plaintext configuration

Agent Services (`/creator/settings`) reads, enters, persists, and hot-reloads:

```text
DeepSeek API Key / Base URL / Model
Image API Key / Base URL / Model / Quality
Tencent Secret ID / Secret Key / Region
Meshy API Key / Input Mode
BCA Public Base URL
```

Contract:

```text
GET /api/v1/creator/config → SETTINGS_READ → plaintext configuration
PUT /api/v1/creator/config → SETTINGS_UPDATE → database write + Agent Provider hot reload
Cache-Control: private, no-store
```

Plaintext values are stored in `bca_creator_*` Bambuddy settings rows. Anyone able to read the database, its backups, or the Creator Config API can read the credentials. Use this mode only with controlled administrator browsers, API clients, databases, and backup locations.

Provider base URLs remain restricted to safe LAN-service HTTP(S) addresses. Unsafe values return HTTP `422`.

## 6. Meshy public URL mode

Recommended default:

```text
MESHY_MODEL_INPUT_MODE=data_uri
```

With:

```text
MESHY_MODEL_INPUT_MODE=public_url
```

`BCA_PUBLIC_BASE_URL` must be a Meshy-reachable public HTTPS origin and reverse-proxy this controlled route:

```text
GET /api/v1/creator/sessions/{session_id}/model.glb
```

This is a high-entropy capability route used only for Meshy GLB retrieval and is not returned in ordinary creator snapshots.

## 7. Reverse proxy and public access

The reverse proxy must forward the static SPA, `/api/v1`, and WebSocket through the same origin to Bambuddy. In production:

- Terminate HTTPS and set `BCA_PUBLIC_BASE_URL` to the external HTTPS origin.
- Trust forwarded headers only from a controlled reverse proxy.
- Never expose Provider credentials, the database, or `DATA_DIR` directly to the Internet.
- Tailscale provides reachability, not application identity; retain Bambuddy authentication and API-key controls.

## 8. Data and backup

Back up these as **one recovery point**:

```text
DATA_DIR/bca-agent/  creator sessions and persisted artifacts
DATA_DIR/bca-tasks/  task source files waiting for slicing
DATA_DIR/archive/    archives and Library files
```

Also back up:

1. The native Bambuddy database: the SQLite database and consistent WAL sidecars, or a complete dump of the PostgreSQL database referenced by `DATABASE_URL`.
2. The `bca_creator_*` plaintext Provider settings, which are native Bambuddy database rows.
3. Required first-start deployment environment and infrastructure configuration.

Restoring only `DATA_DIR` loses `bca_tasks`, Library/queue relationships, and Provider configuration. Restoring only the database loses BCA artifacts. Restore matching database and `DATA_DIR` snapshots together.

Provider signed URLs are not backups; BCA exposes only downloaded, validated, persisted files.

## 9. Queue handoff

BCA emits model 3MF, not a directly printable job. Root must upload a slicer-generated `.gcode.3mf` with:

```text
Metadata/plate_N.gcode
Metadata/slice_info.config
```

After validation, BCA creates a native `LibraryFile`, then creates a native `PrintQueueItem` through `add_to_queue()` with `manual_start=True`. Bambuddy continues to own start/cancel, AMS mapping, printer state, and archival behavior.

## 10. Paid Provider smoke policy

Routine tests must never call billed providers. Non-billed readiness:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_provider_smoke.py --base-url http://127.0.0.1:8000
```

After explicit approval of the applicable charges, run the full flow:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_full_paid_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --confirm-paid `
  --seed-calibration-spool
```

If analysis is not `healthy`, this command stops before the paid Meshy multi-color request. Review the same session's report and resume it instead of repeating GPT Image or Hunyuan:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_full_paid_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --session-id <existing-session-id> `
  --confirm-paid `
  --acknowledge-print-issues `
  --seed-calibration-spool
```

## 11. Health checks and troubleshooting

```text
GET /health                      process liveness
GET /api/v1/creator/config       Creator configuration; plaintext + no-store
```

Useful commands:

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check backend\app backend\tests
npm --prefix .\frontend run lint
npm --prefix .\frontend run test:run
npm --prefix .\frontend run build
```

## 12. References

- [Chinese README](README.md)
- [English README](README.en.md)
- [Chinese architecture](BCA_ARCHITECTURE.zh-CN.md)
- [English architecture](BCA_ARCHITECTURE.md)
- [Chinese engineering contract](AGENTS.zh-CN.md)
- [Documentation audit](DOCUMENTATION_AUDIT.md)
