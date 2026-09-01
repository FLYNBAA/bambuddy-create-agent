# Bambuddy Frontend


[中文](README.zh-CN.md) | **English**
The Bambuddy frontend is a React + TypeScript + Vite single-page administration UI. It is built into the repository-level `static/` directory and served by the FastAPI application; it is not deployed as an independent frontend service.

## Development

From the repository root:

```powershell
npm --prefix .\frontend ci
npm --prefix .\frontend run lint
npm --prefix .\frontend run test:run
npm --prefix .\frontend run build
```

For local API-backed development, start the backend from the repository root:

```powershell
$env:DATA_DIR = "$PWD\data"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
npm --prefix .\frontend run dev
```

### Linux Docker Compose development

From the repository root, use the development Compose stack instead of starting the frontend and backend commands separately:

```bash
docker compose -f docker-compose.dev.yml up --build
```

This is the development-only two-service exception: `frontend` runs Vite with HMR at `http://127.0.0.1:5173`, while `backend` runs Uvicorn with reload at `http://127.0.0.1:8000`. Compose sets `BACKEND_HOST=backend` and `BACKEND_PORT=8000`, so both `/api` and `/api/v1/ws` proxy through Docker service DNS. Native development leaves both variables unset and continues to proxy to `localhost:8000`. The frontend service is not an independently deployable production application.

Use `docker compose -f docker-compose.dev.yml down` to stop the stack. See the repository README for optional Provider environment injection and volume-reset guidance.

## BCA surfaces

The embedded Bambuddy Create Agent UI lives in these pages:

| Route | Component | Purpose |
|---|---|---|
| `/creator` | `pages/CreatorPage.tsx` | Agent conversation, concept-image selection, workflow canvas, artifact download, calibration, and task handoff. |
| `/tasks` | `pages/TaskListPage.tsx` | BCA model tasks, sliced-file attachment, printer selection, and native queue handoff. |
| `/creator/settings` | `pages/CreatorSettingsPage.tsx` | Plaintext Provider credentials, runtime configuration, and hot reload. |

Creator image previews use an authenticated Blob fetch rather than a raw `<img>` source, so they work when Bambuddy authentication is enabled. Do not replace them with unauthenticated provider or artifact URLs.

## Design and contracts

- Keep BCA navigation integrated in `components/Layout.tsx`; do not create a second shell.
- Keep artifact downloads behind controlled BCA routes.
- BCA task files remain model 3MFs until root uploads a validated sliced `.gcode.3mf`.
- Keep API types and frontend state in sync with `backend/app/services/creator_integration.py` and the `creator.py` / `bca_tasks.py` routes.

See the bilingual developer [README](../README.md) / [English README](../README.en.md), [architecture](../BCA_ARCHITECTURE.md), and [engineering guide](../AGENTS.md) for the workflow and non-negotiable gates.
