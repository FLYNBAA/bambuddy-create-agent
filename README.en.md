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

The workflow is driven by Creator cards, not by a separate agent-chat product. A task retains its title, user, customer name, phone, address, notes, intentionally blank price, and model/style previews while it awaits root slicing and queueing. A model 3MF is not a printer job: root attaches the slicer-produced `.gcode.3mf`, BCA validates it, and Bambuddy performs the native queue handoff.

A valid sliced package contains both:

```text
Metadata/plate_N.gcode
Metadata/slice_info.config
```

## BCA pages

| Page | Route | Current responsibility |
|---|---|---|
| Creator | `/creator` | Direct workflow cards, style/model previews, calibration, analysis, and task submission. |
| BCA Tasks | `/tasks` | Task title/user/order context, previews, root slicing attachment, printer selection, and native queue submission. |
| Creator configuration | `/creator/settings` | Provider credentials, models, request endpoints, and runtime settings. |
| Native Bambuddy pages | printers, materials, Library, queue | Authoritative printer, material, Library, and queue behavior. |

Authenticated previews use controlled, Bearer-authenticated Blob fetches; do not expose provider temporary URLs or use a protected artifact route as a raw `<img src>`.

## Provider configuration

Creator configuration can edit the request endpoint/base URL as well as credentials and model settings for DeepSeek, Image2, Hunyuan, and Meshy. This includes the Meshy base URL. Initial deployment values come from the explicit `.env.bca` file; BCA does not read a source-project `.env` or `.env.local`. Persisted creator settings are sensitive database data and must be handled as credentials.

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
