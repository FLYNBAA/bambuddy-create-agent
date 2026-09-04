# Bambuddy Create Agent (BCA)

[中文](README.md) | **English**

BCA is Bambuddy’s embedded 3D-creation workflow. Bambuddy remains the system of record for users, printers, materials, Library files, queues, authentication, and deployment; BCA is not a separate create-agent service or standalone chat UI.

## Direct workflow

```text
Creative presentation (DeepSeek)
  → style image generation (Image2)
  → 3D concept image/model generation (Hunyuan)
  → print calibration
      white, or multicolor 1–8 using Meshy and material color matching
      → final color-calibrated 3MF
  → print analysis (Meshy + DeepSeek score and insights; no advice)
  → order task submission
  → root slicing and native queue handoff
```

BCA operates as an external API capability layer and no longer requires Creator-card workflow orchestration. `/creator` is a one-module test bench: it sends one independent capability request, exposes a data window, and previews returned images and GLBs interactively; a returned 3MF is previewed only through its embedded color snapshot. Public clients compose brief, Image2, image-to-model, multicolor conversion, calibration, and analysis as needed; printer handoff remains root's `.gcode.3mf` plus Bambuddy's native queue.

GLB previews preserve native materials. 3MF is never rendered with ThreeMFLoader in BCA surfaces: the multicolor and calibration modules embed a best-effort colored 512×512 `Metadata/plate_1.png` in the returned 3MF (announced by the `X-BCA-Color-Snapshot` header, `created|present|skipped`), and the test bench previews the artifact through that snapshot. Image2 output is normalized to a 1:1 PNG without stretching the subject.

A valid sliced package contains both:

```text
Metadata/plate_N.gcode
Metadata/slice_info.config
```

## BCA pages

| Page | Route | Current responsibility |
|---|---|---|
| Creator | `/creator` | Independent API module test bench: request, raw data window, image and interactive GLB preview; 3MF previewed through its embedded color snapshot. |
| BCA Tasks | `/tasks` | Legacy task/order context, root slicing attachment, printer selection, and native queue submission. The list shows only the embedded color snapshot from `source_3mf_snapshot_url` (`GET /api/v1/bca-tasks/{id}/snapshot`); `source_3mf_url` still downloads the full model 3MF. Direct `POST /api/v1/bca-tasks` accepts a model `.3mf` and rejects GLB and sliced `.gcode.3mf` files. |
| Creator configuration | `/creator/settings` | Write-only provider credentials, non-secret runtime settings, and provider state. |
| Native Bambuddy pages | printers, materials, Library, queue | Authoritative printer, material, Library, and queue behavior. |

Authenticated previews use controlled, Bearer-authenticated Blob fetches; do not expose provider temporary URLs or use a protected artifact route as a raw `<img src>`.

## Provider configuration

Creator configuration returns non-secret runtime values and provider state only; credentials are write-only and never echoed by GET or save responses. Initial deployment values come from explicit `.env.bca`; BCA does not read a source-project `.env` or `.env.local`. Persisted creator settings are sensitive database data and must be handled as credentials.

## Deployment and discovery

- Linux Compose builds the local BCA source into the local `bambuddy-bca:local` image and uses an explicit `.env.bca` file.
- Linux host-network deployments retain SSDP discovery for the printer LAN.
- Windows Docker Desktop and other bridge deployments use declared `BCA_DISCOVERY_SUBNETS` CIDRs and unicast discovery scans instead of relying on broadcast discovery.
- Tailscale provides reachability only. Reach printer LANs through an externally operated subnet router, or colocate BCA on that LAN. BCA does not enroll itself as a subnet router and does not issue certificates.
- The production reverse-proxy template is [`deploy/nginx/bca.conf`](deploy/nginx/bca.conf). It keeps upstream authentication intact and forwards WebSocket and forwarded-request headers.

See [Deployment](DEPLOYMENT_BCA.md) for the supported topology, recovery, rollback, and verification procedure.

## Backup and rollback

Back up `DATA_DIR` and the Bambuddy database as one matching recovery point. That includes creator artifacts, task sources, Library/queue relationships, and persisted provider configuration. For a rollback, use a known-compatible local-source revision; if data compatibility is uncertain, restore the matching database and `DATA_DIR` recovery point together. Do not restore either side independently.

## Billed-provider smoke policy

The product UI has no payment-confirmation or issue-acknowledgement gates. Routine checks must not call billed providers. A billed-provider invocation is allowed only after a human explicitly approves the applicable run and charges at invocation time; do not treat a prior UI action or a reusable flag as product confirmation. Print analysis reports score and insights without advice.

## Current boundary

BCA is currently single-process. Do not claim multi-worker, distributed queue recovery, multi-user ownership isolation, automatic Tailscale subnet routing, or automatic TLS/certificate provisioning.

## References

- [中文 README](README.md)
- [Architecture](BCA_ARCHITECTURE.md)
- [Deployment](DEPLOYMENT_BCA.md)
- [Documentation audit](DOCUMENTATION_AUDIT.md)
- [Frontend guide](frontend/README.md)
