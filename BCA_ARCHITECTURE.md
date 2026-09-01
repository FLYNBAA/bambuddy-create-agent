# BCA Architecture

[中文](BCA_ARCHITECTURE.zh-CN.md) | **English**

## Scope

BCA is the embedded, single-process creator workflow within Bambuddy. Bambuddy remains authoritative for identities, printers, materials, Library files, native queue dispatch, authentication, WebSocket transport, and deployment. BCA owns creator state, generated artifacts, calibration, analysis, and order-task handoff; it is neither a separate service nor a standalone agent-chat UI.

## Workflow and handoff

```text
Creative presentation (DeepSeek)
  → style image (Image2)
  → 3D concept image/model (Hunyuan)
  → calibration: white or multicolor 1–8
      Meshy + Bambuddy material color matching → color-calibrated 3MF
  → analysis: Meshy + DeepSeek score and insights, without advice
  → order task submission
  → root attaches validated sliced .gcode.3mf
  → Bambuddy LibraryFile and native PrintQueueItem
```

A task preserves title, user, customer name, phone, address, notes, a nullable price (currently blank), and model/style previews while pending root slicing and queueing. Creator model 3MF files never reach a printer directly. The root-supplied sliced package must contain `Metadata/plate_N.gcode` and `Metadata/slice_info.config` before BCA can hand it to the native queue.

## Creator and task responsibilities

| Area | Responsibility |
|---|---|
| Creator cards | Run the direct staged workflow; show style and model previews; create calibrated artifacts, analysis, and order tasks. |
| Calibration | Produce either a white 3MF or a 1–8-color 3MF using Meshy and Bambuddy material-color matching. The final multicolor output is the color-calibrated 3MF. |
| Analysis | Obtain Meshy data and DeepSeek scoring/insights. It does not produce user-facing advice. |
| BCA task | Retain title, user, order, and previews until root adds the validated slice and selects a printer. |
| Bambuddy | Own Library files, printer selection, queue lifecycle, dispatch, cancellation, and printer state. |

## API and configuration boundary

Creator and task routes remain within the Bambuddy application and its authorization model. Normal artifact downloads are controlled; provider temporary URLs and server filesystem paths are not frontend contracts.

The Creator configuration page (`/creator/settings`) can update provider credentials, models, and request endpoints/Base URLs for DeepSeek, Image2, Hunyuan, and Meshy, including the Meshy base URL. Deployment values seed configuration through explicit `.env.bca`; BCA does not discover source-project `.env` or `.env.local` files. Persisted provider settings are sensitive Bambuddy database data.

## Approval and safety boundary

The product UI contains no paid confirmation or issue-acknowledgement gates. Routine verification does not invoke billed providers. Any billed-provider run requires explicit human approval for that invocation and its charges at the point of execution. This operational approval is not a workflow-card gate. Print analysis supplies score and insights without advice.

## Deployment boundary

Linux Compose builds the local source into `bambuddy-bca:local` and uses explicit `.env.bca`. Linux host networking retains SSDP discovery. Windows Docker Desktop and other bridge networks use declared `BCA_DISCOVERY_SUBNETS` CIDRs and unicast scans.

For a public origin or Meshy public-URL input, use the production reverse-proxy template at `deploy/nginx/bca.conf`. It preserves upstream authentication and forwards WebSocket and forwarded-request headers. Tailscale supplies network reachability only: printer-LAN access requires an external subnet router or BCA colocated on that LAN. BCA does not auto-enroll as a subnet router and does not provide certificates.

## Persistence, recovery, and limits

Back up and restore the matching `DATA_DIR` and Bambuddy database together: creator artifacts, task sources, persisted configuration, and Library/queue relationships must not diverge. Roll back only to a known-compatible local-source revision; when compatibility is uncertain, restore the matching recovery point.

The current implementation remains single-process. Multi-worker scheduling, distributed locks, durable worker recovery, multi-user ownership isolation, object storage, and verified provider webhooks are not current behavior.

## References

- [中文架构说明](BCA_ARCHITECTURE.zh-CN.md)
- [Deployment](DEPLOYMENT_BCA.md)
- [English README](README.en.md)
- [Documentation audit](DOCUMENTATION_AUDIT.md)
