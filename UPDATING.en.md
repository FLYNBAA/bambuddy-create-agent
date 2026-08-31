# Updating BCA

[中文](UPDATING.md) | **English**

This guide applies to the `bambuddy-create-agent` fork. Do not update with upstream Bambuddy repository URLs, historic image tags, or upstream installer scripts: they do not contain the BCA code, documentation, or configuration contracts.

## Mandatory pre-update backup

Create one recovery point containing:

```text
DATA_DIR
Native Bambuddy database (SQLite + WAL, or PostgreSQL dump)
bca_creator_* plaintext Provider configuration
Required deployment environment configuration
```

`bca_tasks` and `bca_creator_*` live in the native database. BCA sessions and artifacts live in `DATA_DIR`. Restore both from matching snapshots.

## Updating a Git working tree

From the BCA repository root:

```bash
# Confirm this is your BCA fork before changing it.
pwd
git remote -v
git status

# Fetch and inspect BCA fork commits.
git fetch origin
git log --oneline HEAD..origin/main

# Merge only after preserving/reviewing local deployment work.
git merge --ff-only origin/main
```

Update dependencies and build:

```bash
.venv/bin/python -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
npm --prefix .\frontend ci
npm --prefix .\frontend run build
```

The application performs database migrations on startup. Afterwards verify:

```text
GET /health
GET /api/v1/creator/config
```

`/api/v1/creator/config` returns plaintext Provider values. Access it only from controlled administrator browsers or API clients; it is `private, no-store`.

## Updating Docker

From the BCA repository root:

```bash
# Back up data and the database first.
# Build the current BCA checkout; do not pull an upstream-only image.
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f bambuddy
```

Windows Docker Desktop:

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml build
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d
curl http://127.0.0.1:8012/health
```

For an ordinary stop:

```bash
docker compose down
```

Do not use `docker compose down -v` on a deployment with data because it deletes named data volumes. It is only appropriate for an intentionally disposable smoke stack.

## Post-update verification

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_creator_config_api.py -q
.\.venv\Scripts\ruff.exe check backend\app backend\tests
npm --prefix .\frontend run lint
npm --prefix .\frontend run build
```

In the running application:

1. Open `/creator/settings` and confirm Provider parameters and plaintext credentials recovered as intended.
2. Open `/tasks` and confirm task and sliced-file handoff state exists.
3. Check native printer and queue pages.
4. Do not automatically invoke paid Providers after an update; follow the approved smoke policy in the [deployment guide](DEPLOYMENT_BCA.md).

## Rollback

1. Stop the current process/container.
2. Check out or build a known-working BCA revision.
3. Restore the database and `DATA_DIR` together from the same recovery point.
4. Use a controlled administrator session to confirm Agent Services configuration and Provider credentials.
5. Start the app and check `/health`, creator, tasks, and native queue workflows.

## References

- [Chinese README](README.md)
- [English deployment guide](DEPLOYMENT_BCA.md)
- [English engineering contract](AGENTS.md)
