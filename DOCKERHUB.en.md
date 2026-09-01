# BCA Docker Images and Compose

[中文](DOCKERHUB.md) | **English**

BCA is built from the current `bambuddy-create-agent` working tree. Do not pull an upstream `maziggy/bambuddy` public image and expect BCA creator, calibration, task, or plaintext-configuration functionality.

## Recommended runtime

Linux:

```bash
docker compose --env-file .env.bca up -d --build
docker compose ps
docker compose logs -f bambuddy
```

Windows Docker Desktop:

```powershell
docker compose --env-file .env.bca -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d --build
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

Linux defaults to host networking and retains SSDP. Windows Docker Desktop uses the bridge override; `BCA_DISCOVERY_SUBNETS` in `.env.bca` enables unicast scanning of explicit private/Tailscale-routed CIDRs, while Virtual Printer/passive FTP still needs deliberate extra port mappings.

See the full [English deployment guide](DEPLOYMENT_BCA.md) for reverse proxy, plaintext configuration, backup, and smoke policy.
