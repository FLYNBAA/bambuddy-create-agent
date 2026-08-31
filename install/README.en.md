# BCA Installation Scripts

[中文](README.md) | **English**

This directory contains inherited Bambuddy installation foundations. BCA deployment must use the current BCA fork working tree, its Compose files, and repository documentation. Do not download upstream `maziggy/bambuddy` installation scripts and expect BCA functionality.

## Recommended installation paths

### Linux Docker

From the BCA fork working tree:

```bash
docker compose up -d --build
```

Linux production defaults to host networking for discovery, Virtual Printer, cameras, and LAN protocols.

### Windows Docker Desktop

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d --build
curl http://127.0.0.1:8012/health
```

Windows bridge mode requires printer LAN IP setup. For an ordinary stop:

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml down
```

Do not use `down -v` for a deployment that retains data.

### Local Python development/testing

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
npm --prefix .\frontend ci
npm --prefix .\frontend run build
$env:DATA_DIR = "$PWD\data"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

## Current script scope

| Script | Native responsibility | BCA use |
|---|---|---|
| `install.sh` | Linux/macOS native Bambuddy install | Run only in the BCA fork after verifying BCA dependencies and static build. |
| `docker-install.sh` | Linux/macOS Docker bootstrap | Do not download upstream Compose; use this fork's `docker-compose.yml`. |
| `docker-install.ps1` | Windows Docker Desktop bootstrap | BCA additionally requires the `docker-compose.windows.yml` override. |
| `windows-installer.ps1` | Native Windows service install | Requires BCA fork content, BCA dependencies, and the current frontend build. |
| `update.sh` | systemd native update | Back up the native database and `DATA_DIR` first; see [Updating BCA](../UPDATING.en.md). |

## Post-install BCA setup

1. Complete Bambuddy Setup and establish controlled administrator access.
2. Use `/creator/settings` to enter or confirm Provider parameters and plaintext credentials.
3. Record that these values persist as `bca_creator_*` Bambuddy database rows.
4. Add printers and filament inventory.
5. Create sessions at `/creator` and retain every payment confirmation gate.
6. At `/tasks`, attach root-sliced `.gcode.3mf` before native queue handoff.

See the full [English deployment guide](../DEPLOYMENT_BCA.md) for network, reverse-proxy, backup, PostgreSQL, and billed smoke requirements.
