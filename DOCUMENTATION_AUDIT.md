# Documentation Audit

[中文](DOCUMENTATION_AUDIT.zh-CN.md) | **English**

## Scope and paired documents

This inventory covers the BCA-specific Markdown documents that define current workflow, configuration, architecture, deployment, and frontend behavior. English and Chinese documents are paired at their headings:

| English | 中文 | Current purpose |
|---|---|---|
| [README.en.md](README.en.md) | [README.md](README.md) | Direct BCA workflow, operational boundary, topology summary, recovery, and billed-run approval policy. |
| [BCA_ARCHITECTURE.md](BCA_ARCHITECTURE.md) | [BCA_ARCHITECTURE.zh-CN.md](BCA_ARCHITECTURE.zh-CN.md) | Workflow ownership, task handoff, configuration, safety, persistence, and system boundary. |
| [DEPLOYMENT_BCA.md](DEPLOYMENT_BCA.md) | [DEPLOYMENT_BCA.zh-CN.md](DEPLOYMENT_BCA.zh-CN.md) | Local-source Compose deployment, discovery, proxy topology, Tailscale boundary, recovery, rollback, and verification. |
| [frontend/README.md](frontend/README.md) | [frontend/README.zh-CN.md](frontend/README.zh-CN.md) | Embedded frontend surfaces and BCA UI/data contracts. |
| [DOCUMENTATION_AUDIT.md](DOCUMENTATION_AUDIT.md) | [DOCUMENTATION_AUDIT.zh-CN.md](DOCUMENTATION_AUDIT.zh-CN.md) | This audit inventory and stale-claim replacement record. |

## Current cross-document contract

- BCA’s direct order is Creative presentation (DeepSeek) → style image (Image2) → 3D concept image/model (Hunyuan) → white or 1–8-color calibration using Meshy and material color matching → final color-calibrated 3MF → Meshy + DeepSeek score/insights without advice → order task submission.
- Tasks retain title, user, order, model preview, and style preview while awaiting root slicing and native queueing. Model 3MF is not directly printable; root supplies the validated sliced `.gcode.3mf`.
- Creator configuration edits provider request endpoints/Base URLs, including the Meshy base URL, alongside credentials and model settings. Explicit `.env.bca` provides deployment initial values; source-project `.env` and `.env.local` are not BCA configuration inputs.
- Linux Compose builds local BCA source as `bambuddy-bca:local` and uses explicit `.env.bca`. Linux host networking retains SSDP. Windows and bridge deployments use declared `BCA_DISCOVERY_SUBNETS` CIDRs and unicast scans.
- The supported Nginx template is [`deploy/nginx/bca.conf`](deploy/nginx/bca.conf); it preserves upstream authentication and forwards WebSocket and forwarded-request headers.
- Tailscale supplies reachability only. Printer-LAN access needs an external subnet router or BCA colocated on the LAN. BCA does not auto-enroll as a subnet router and does not provide certificates.
- Backup/restore treats `DATA_DIR` and the matching Bambuddy database as one recovery point. Rollback uses a known-compatible local-source revision or restores that matching recovery point.
- Product UI has no paid confirmation or issue-acknowledgement gates. Billed-provider smoke runs require explicit human approval for the specific invocation and charges at execution time.

## Retired stale claims

The targeted documents must not describe any of the following as current BCA behavior:

| Retired claim | Current replacement |
|---|---|
| A confirmation/payment gate before creator image, 3D, calibration, or analysis cards. | Product UI has no paid or issue-acknowledgement gates; billed operational runs require human approval at invocation. |
| A non-healthy report blocks work behind a user issue acknowledgement. | Analysis reports score and insights without advice; there is no issue-acknowledgement gate. |
| Four-image GPT Image flow or a standalone Agent chat UI. | The documented workflow uses direct creator cards with DeepSeek, Image2, and Hunyuan. |
| BCA task loses context before slicing. | Title, user, customer/phone/address/notes, blank price, and style/model previews remain pending root slicing/queueing. |
| Provider endpoints are fixed or Meshy base URL cannot be configured. | Creator configuration edits each provider request endpoint/Base URL, including Meshy. |
| Current BCA pulls an upstream prebuilt Docker image or discovers dotenv implicitly. | Compose builds local source as `bambuddy-bca:local` and uses explicit `.env.bca`. |
| Bridge deployments rely on SSDP broadcast. | Bridge deployments scan declared `BCA_DISCOVERY_SUBNETS` by unicast; Linux host networking keeps SSDP. |
| Tailscale automatically makes BCA a subnet router or supplies certificates. | Operators provide external routing/certificates, or colocate BCA on the printer LAN. |
| An arbitrary Nginx configuration is the reference topology. | `deploy/nginx/bca.conf` is the BCA production template with upstream auth and WebSocket/forwarded-header support. |
| Backup or rollback can restore database and data independently. | Restore the matching database and `DATA_DIR` recovery point together. |

## Out-of-scope documents

Generic Bambuddy historical, governance, or upstream-derived documents are not evidence for BCA behavior unless this inventory explicitly links them. They must not override these paired BCA documents.
