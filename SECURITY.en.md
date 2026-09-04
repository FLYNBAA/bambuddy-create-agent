# BCA Security Policy

[中文](SECURITY.md) | **English**

This policy applies to `bambuddy-create-agent`. Report security issues through the current BCA fork's private maintainer channel. Do not put real Provider credentials, printer access codes, database backups, or artifact URLs in public issues, screenshots, logs, or documentation.

## Report content

Include:

- Vulnerability description and impact;
- Reproducible steps and a minimal PoC;
- Affected BCA/Bambuddy version and deployment topology;
- Whether authentication, a specific permission, network position, or database access is required;
- A suggested fix, if available.

## BCA security boundaries

### Routes and permissions

- Authentication and authorization use Bambuddy's native model.
- Plaintext `GET /api/v1/creator/config` and hot-reloading `PUT` both require `SETTINGS_UPDATE`; read-only status/API-key scopes cannot retrieve Provider secrets.
- Ordinary browser artifact downloads require permissions. Meshy `public_url` uses a separate unguessable Provider capability token which is neither the session ID nor returned in snapshots/WebSocket events.
- New routes require an explicit auth dependency or a documented reason in the public-route allowlist.

### Plaintext Provider configuration

The current product permits browser, API, and Bambuddy database storage of plaintext Provider values:

```text
DeepSeek API Key
Image API Key
Tencent Secret ID / Secret Key
Meshy API Key
```

The boundary is authorization, not confidential-at-rest storage: a principal with `SETTINGS_READ`, database-read access, or a database backup can read these values. To prevent cache exposure, config GET/PUT responses must send:

```text
Cache-Control: private, no-store
```

Do not write credentials to ordinary creator snapshots, tasks, Provider errors, logs, test fixtures, public documentation, or uncontrolled clients.

### Network and downloads

- Provider base URLs must pass LAN-service HTTP(S) URL safety checks. Dangerous schemes, metadata endpoints, numeric encoded IPs, and similar targets are rejected.
- User and Provider URL downloads keep domain, redirect, and path-security boundaries.
- `MESHY_MODEL_INPUT_MODE=public_url` uses configured HTTPS `BCA_PUBLIC_BASE_URL` plus independent, unguessable Provider capability tokens. These capability URLs are for Meshy only and are never returned to browser/session clients.

### Files and 3MF

- Path joins use `safe_join_under` or explicit resolve/containment checks.
- Uploads validate content. BCA 3MF uploads (task model files, sliced packages, and calibration/source packages) share the 512 MiB calibration package limit and validate ZIP member count, duplicate members, compression ratio, decompressed size, and required files.
- A model 3MF must pass `.gcode.3mf` validation before native queue handoff.

### Billing and Providers

- Product UI has no billed-confirmation or issue-acknowledgement gates. Paid POSTs are never automatically retried; callers must inspect session state rather than retry after an ambiguous network outcome.
- `brief/prepare` follows the caller's source language and always returns its final prompt bundle for accepted input. It has no clarification/type-choice or presentation-stream gate; compatibility `questions` is empty and `image_prompt_ready` is true.
- Multicolor calibration reads only active eligible `spool` rows, not `color_catalog`; successful mapping requires non-empty `assignments` and a final artifact.
- Do not copy real paid credentials or request/response bodies into public reports.

## Contributor checks

Security changes require negative-path tests for missing permissions, insufficient permissions, unsafe URLs, path escape, invalid state transition, or missing cache headers. See the [English engineering contract](AGENTS.md) and [English contribution guide](CONTRIBUTING.en.md).
