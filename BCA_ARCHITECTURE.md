# BCA Architecture

[中文](BCA_ARCHITECTURE.zh-CN.md) | **English**

## Scope

BCA is Bambuddy's embedded API capability layer for creation assets. Bambuddy remains authoritative for identities, printers, materials, Library files, native queue dispatch, authentication, WebSocket transport, and deployment. Creator exposes independently callable brief, Image2, image-to-GLB, GLB-to-3MF, 3MF calibration, and analysis modules; legacy sessions remain a compatibility adapter, not the public integration model.

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

A task preserves title, user, customer name, phone, address, notes, an optional price supplied by the session push or direct upload, a style image, and its embedded color 3MF snapshot while pending root slicing and queueing. The task UI does not render a full model. Creator model 3MF files never reach a printer directly. The root-supplied sliced package must contain `Metadata/plate_N.gcode` and `Metadata/slice_info.config` before BCA can hand it to the native queue.

### Source-language prompt contract

The latest creative message determines the entire response language: Chinese input returns Chinese brief values, display copy, and prompt bundle; English input returns English equivalents. Brief preparation always auto-completes and returns final prompts; once `subject`, `style`, and `product_type` are complete, BCA derives `positive_prompt`, `negative_prompt`, `print_constraints`, and one deterministic `image2_prompt`. There is no clarification or type-choice path, and the compatibility `questions` field is always empty. The fixed Image2 clauses explicitly constrain composition, printability, exclusions, and output boundary; the test bench exposes the complete bundle and seeds its Image2 field from `image2_prompt`.

## Creator and task responsibilities

| Area | Responsibility |
|---|---|
| Creator API modules | Execute one explicitly requested capability; never create or advance a workflow for the caller. |
| Creator test bench | Send one module request, show raw response metadata/JSON, and preview returned images and GLBs interactively; preview a 3MF only through its embedded color snapshot. |
| Calibration | Convert GLB to 1–8-color 3MF, then separately match 3MF colors to Bambuddy material inventory. The multicolor and calibration artifacts embed a best-effort colored 512×512 `Metadata/plate_1.png` snapshot. |
| Analysis | Obtain Meshy data and DeepSeek scoring/insights. It does not produce user-facing advice. |
| BCA task | Legacy handoff retaining title, user, order, and previews until root adds the validated slice and selects a printer. The task API keeps `source_3mf_url` for the full 3MF and adds `source_3mf_snapshot_url` for the embedded snapshot; the task UI displays only that snapshot, never rendered 3MF geometry. |
| Bambuddy | Own Library files, printer selection, queue lifecycle, dispatch, cancellation, and printer state. |

## API and configuration boundary

Creator and task routes remain within the Bambuddy authorization model. Public module clients use queue-scoped API keys; normal artifact downloads are controlled; provider temporary URLs and server filesystem paths are never frontend contracts.

`/creator/settings` is administrator-only. Provider secrets are write-only: `GET` returns non-secret runtime values and `configured` state, while `PUT` accepts secret replacements without echoing them. Deployment values seed configuration through explicit `.env.bca`; BCA does not discover source-project `.env` or `.env.local` files.

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
