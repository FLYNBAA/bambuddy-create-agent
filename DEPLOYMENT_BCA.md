# BCA Deployment

## Local Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
npm --prefix .\frontend ci
npm --prefix .\frontend run build
$env:DATA_DIR = "$PWD\data"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Use the Agent Services page to hot-reload non-secret provider values. Provider base URLs must be valid LAN-service HTTP(S) URLs; unsafe values are rejected with HTTP `422`. Supply provider secrets through the process environment; do not put them in browser requests, database settings, committed files, or task records. BCA does not load source-project `.env` or `.env.local` files.

## Linux Docker

The existing multi-stage `Dockerfile` builds the React application into `/app/static` and installs the BCA additions from `requirements.txt`. The existing Compose file remains the deployment entry point.

```bash
docker compose up -d --build
```

Recommended production settings:

```text
DATA_DIR=/app/data
LOG_DIR=/app/logs
BCA_PUBLIC_BASE_URL=https://bca.example.example
DEEPSEEK_API_KEY=<secret manager value>
IMAGE_API_KEY=<secret manager value>
TENCENT_SECRET_ID=<secret manager value>
TENCENT_SECRET_KEY=<secret manager value>
MESHY_API_KEY=<secret manager value>
```

### Windows Docker Desktop override

Docker Desktop cannot use the Linux production `network_mode: host`. Use the committed override:

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml build
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d
curl http://127.0.0.1:8012/health
curl http://127.0.0.1:8012/api/v1/creator/config
```

`docker-compose.windows.yml` uses Compose `!reset null` to remove host networking and publishes host port `8012` by default. Override it with `BCA_DOCKER_PORT` if necessary. Do not set it to a port occupied by another local BCA/Bambuddy process.

On Windows bridge networking, add printers by LAN IP. SSDP discovery and the full Virtual Printer passive FTP range require additional explicit mappings and are not covered by the single-port smoke override.

`BCA_PUBLIC_BASE_URL` is only required when Meshy is configured to fetch source GLB via a public URL. It must resolve to the reverse-proxied public origin and expose `GET /api/v1/creator/sessions/{session_id}/model.glb` over HTTPS. This high-entropy provider capability route is not returned in normal creator snapshots.

## Networking

- Linux `network_mode: host` is the default because printer discovery, Virtual Printer, camera and LAN transport work most reliably there.
- Bridge mode is supported with the documented port mapping. It cannot perform SSDP discovery; add printers by IP and configure passive FTP ports.
- Tailscale is optional. It is a network layer, not an application identity layer; keep Bambuddy authentication/API keys enabled for public or tailnet access.

## Data and backup

```text
DATA_DIR/bca-agent/  creator snapshots and model artifacts
DATA_DIR/bca-tasks/  calibration artifacts awaiting a sliced file
DATA_DIR/archive/    Bambuddy archives and Library files
```

Back up `DATA_DIR`, the deployment secret configuration, **and the native Bambuddy database** as one recovery point. For SQLite, include the database file and any required WAL sidecars consistently. For PostgreSQL, take a complete PostgreSQL dump of the configured `DATABASE_URL` database.

`bca_tasks` and persisted `bca_creator_*` service settings live in the native Bambuddy database, including when `DATABASE_URL` points to external PostgreSQL. Restoring only `DATA_DIR` loses task rows and configuration; restoring only the database loses creator artifacts. Restore the matching database snapshot and `DATA_DIR` together. Provider signed URLs are never backup artifacts: BCA persists validated files before exposing them.

## Queue contract

A BCA geometry or multi-color-calibrated model remains a model 3MF. Root must supply a slicer-produced `.gcode.3mf` containing `Metadata/plate_N.gcode` and `Metadata/slice_info.config` before BCA creates a Bambuddy `PrintQueueItem`.


## Verified Windows Docker result

Docker Desktop Engine and Compose successfully built the BCA image and started the Windows bridge override. The first Windows checkout exposed a CRLF shell-script problem: Linux interpreted the entrypoint shebang as `/bin/sh\r` and reported the script as missing. `Dockerfile` now normalizes `docker-entrypoint.sh` with `sed -i 's/\r$//'` before execution.

The rebuilt container reached Docker health `healthy`; the host verified:

```text
GET /health
GET /api/v1/creator/config
```

The smoke compose stack was removed with `down -v` after validation. The public Windows test mapping is `8012:8000`.

## Authorized provider result

An explicitly approved full paid-chain smoke completed on 2026-08-29 after deployment-time provider credentials were injected. The runner persisted exactly four GPT Image candidates, a Hunyuan GLB, Meshy print analysis, a Meshy multi-color 3MF, its geometry-normalized 3MF, and a DeepSeek-calibrated 3MF. It created the related calibrated-artifact task. The temporary local PLA calibration spool was deleted after the run.

The successful session remained `completed`; `print_analysis`, `print_file`, `geometry_status`, and `color_calibration` all reached `succeeded`. The runner made no queue submission: a BCA-generated model 3MF must still be sliced to a validated `.gcode.3mf` before native Bambuddy queue handoff.

The former image-relay HTTP 401 was resolved by the subsequent approved credential/base-URL configuration. Do not rely on that old relay credential; inject current rotated deployment credentials at runtime.

## Provider smoke policy

The safe default only reports provider configuration:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_provider_smoke.py --base-url http://127.0.0.1:8000
```

After a human explicitly approves only the billed GPT Image request and the running BCA process has deployment-time secrets, use:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_provider_smoke.py --base-url http://127.0.0.1:8000 --confirm-paid
```

The runner deliberately stops after the four-image paid request is accepted. It does not submit Hunyuan or Meshy work, so it cannot accidentally spend 3D or multi-color credits.

For a separately approved full chain, use the full runner. It performs image and Hunyuan stages, then also submits Meshy multi-color work only when analysis is `healthy`:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_full_paid_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --confirm-paid `
  --seed-calibration-spool
```

When analysis returns any status other than `healthy`, the initial full runner stops before the Meshy paid request. Review the session's report, then use the resume command below with `--acknowledge-print-issues` as a distinct approval. `--seed-calibration-spool` provides and then removes an isolated PLA candidate needed for DeepSeek calibration.

If a non-healthy report stops a full run, do not repeat GPT Image or Hunyuan. After reviewing the existing session's report, resume only the paid Meshy stage:

```powershell
.\.venv\Scripts\python.exe .\backend\tools\bca_full_paid_smoke.py `
  --base-url http://127.0.0.1:8000 `
  --session-id <existing-session-id> `
  --confirm-paid `
  --acknowledge-print-issues `
  --seed-calibration-spool
```

## References

- Bilingual developer README: [`README.md`](README.md) / [`README.en.md`](README.en.md)
- Architecture: [`BCA_ARCHITECTURE.md`](BCA_ARCHITECTURE.md)
- Non-secret variable template: [`.env.bca.example`](.env.bca.example)
