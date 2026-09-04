# BCA Deployment Guide

[中文](DEPLOYMENT_BCA.zh-CN.md) | **English**

BCA is deployed as part of Bambuddy: one application, one frontend origin, and Bambuddy’s existing identity, queue, and printer authority. Do not deploy a second create-agent service, a standalone agent-chat UI, or an upstream prebuilt image as the current BCA deployment.

## 1. Supported Compose topologies

### Linux printer-LAN deployment

Linux Compose builds the local repository source as `bambuddy-bca:local`. Use the explicit BCA environment file rather than implicit project dotenv discovery:

```bash
docker compose --env-file .env.bca up -d --build
```

The Linux topology uses host networking and retains SSDP for printer-LAN discovery. `.env.bca` supplies first-start deployment values; it is not a substitute for secure credential handling and must not be committed.

### Windows Docker Desktop or other bridge deployment

Use the bridge override and a declared discovery target set:

```powershell
docker compose --env-file .env.bca -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d --build
```

Set `BCA_DISCOVERY_SUBNETS` to the CIDRs that BCA may scan, for example the relevant private LAN and, if applicable, Tailscale CGNAT range. Bridge deployments use unicast scans; they do not depend on SSDP broadcast discovery. Add direct printer LAN IPs when appropriate. Do not imply that bridge mode has host-network multicast behavior.

Use ordinary Compose stop/removal for normal shutdown. Do not remove data volumes when the deployment data must be retained.

## 2. Provider configuration

Creator configuration at `/creator/settings` edits non-secret runtime parameters and accepts write-only credential replacements for DeepSeek, Image2, Hunyuan, and Meshy. `GET /api/v1/creator/config` never returns credentials; it returns runtime values and `configured` state only. The explicit `.env.bca` file provides initial deployment values; BCA does not read source-project `.env` or `.env.local` files.

Persisted creator configuration remains sensitive database state. Keep the configuration page, database, backups, and `.env.bca` under administrator control. Do not put credentials in task records, previews, source code, or public documentation.

Public integrations should use the independently callable `/api/v1/creator/modules/*` capability routes documented in `BCA_INTEGRATION_GUIDE.md`. The `/creator` page is a test bench for one request at a time, not a workflow orchestrator.

## 3. Reverse proxy and public origin

The repository production Nginx template is [`deploy/nginx/bca.conf`](deploy/nginx/bca.conf). Use it as the topology reference for serving the static application and proxying API/WebSocket traffic to Bambuddy. It preserves upstream authentication and forwarded headers, disables proxy buffering for artifacts/uploads, and sets 1000-second API read/send timeouts because Meshy/Hunyuan module calls may take up to 900 seconds.

Before rollout, download a protected large 3MF through the deployed HTTPS/Nginx origin and compare both `Content-Length` and SHA-256 with the persisted file. This validates the proxy path; an in-process FastAPI test alone is insufficient.

## 4. Tailscale and discovery

Tailscale provides network reachability, not application authentication, TLS certificates, or printer-LAN routing. Retain Bambuddy authentication and API-key controls. To reach printers behind another LAN, operate an external Tailscale subnet router, or run BCA on that printer LAN. BCA neither auto-enrolls as a subnet router nor advertises routes itself.

## 5. Workflow, task, and native queue handoff

The direct workflow is Creative presentation (DeepSeek) → style image (Image2) → 3D concept image/model (Hunyuan) → white or 1–8-color calibration (Meshy plus material color matching) → Meshy + DeepSeek score/insights without advice → order task submission.

Tasks retain title, user, customer name, phone, address, notes, an optional price supplied by the session push or direct upload, and previews until root slicing and queueing. The task API keeps `source_3mf_url` for downloading the full model 3MF and adds `source_3mf_snapshot_url` for `GET /api/v1/bca-tasks/{id}/snapshot`, which returns only the embedded `Metadata/plate_1.png` color snapshot (404 when absent); the task UI displays that snapshot rather than rendered 3MF geometry. A model 3MF is not printable directly. Root attaches a slicer-produced `.gcode.3mf` containing:

```text
Metadata/plate_N.gcode
Metadata/slice_info.config
```

After validation, Bambuddy receives the native Library/queue handoff and continues to own printer control and queue lifecycle.

## 6. Backup, restore, and rollback

Create one recovery point containing both:

1. `DATA_DIR`, including creator artifacts and task source files.
2. The matching Bambuddy database, including persisted provider settings and Library/queue relationships.

Restore these together. Restoring only data files or only the database can detach tasks and artifacts from native Library and queue records. A source rollback must use a known-compatible local-source revision; when data compatibility is uncertain, restore the matching recovery point rather than mixing revisions with newer data.

## 7. Verification guidance

Verify deployment behavior through the actual topology: the application health endpoint, authenticated application access through the configured proxy, the intended discovery method (SSDP on Linux host networking or declared-subnet unicast on bridge), and root slice-to-native-queue handoff. These checks do not require billed providers.

Routine verification must not invoke billed providers. A billed-provider smoke run requires explicit human approval at the time that specific invocation and its charges are authorized. This is an operator approval for the run, not a product-UI paid confirmation gate; the UI also has no issue-acknowledgement gate. Print analysis returns score and insights without advice.

## References

- [中文部署指南](DEPLOYMENT_BCA.zh-CN.md)
- [Architecture](BCA_ARCHITECTURE.md)
- [English README](README.en.md)
- [Documentation audit](DOCUMENTATION_AUDIT.md)
