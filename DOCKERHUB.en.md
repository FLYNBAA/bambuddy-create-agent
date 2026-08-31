# BCA Docker Images and Compose

[中文](DOCKERHUB.md) | **English**

BCA is built from the current `bambuddy-create-agent` working tree. Do not pull an upstream `maziggy/bambuddy` public image and expect BCA creator, calibration, task, or plaintext-configuration functionality.

## Recommended runtime

Linux:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f bambuddy
```

Windows Docker Desktop:

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d --build
curl http://127.0.0.1:8012/health
```

For an ordinary stop:

```bash
docker compose down
```

Do not use `down -v` on an environment with data because it deletes named data volumes.

## Container data

```text
/app/data  database or data layout, BCA sessions, 3MF, tasks, and archives
/app/logs  application logs
```

With external PostgreSQL, the database is not in `/app/data`. Back up the PostgreSQL dump, `DATA_DIR`, and database-resident `bca_creator_*` plaintext Provider settings together.

## Networking

Linux defaults to host networking. Windows Docker Desktop uses bridge override and requires manual printer LAN IP setup plus extra mappings where Virtual Printer/passive FTP capabilities are needed.

See the full [English deployment guide](DEPLOYMENT_BCA.md) for reverse proxy, plaintext configuration, backup, and smoke policy.
