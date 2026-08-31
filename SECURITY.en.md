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
- `GET /api/v1/creator/config` requires `SETTINGS_READ`; `PUT` requires `SETTINGS_UPDATE`.
- Ordinary creator artifact downloads use controlled routes and permissions. Meshy's `public_url` GLB capability route is an exception and is not returned in normal session snapshots.
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
- `MESHY_MODEL_INPUT_MODE=public_url` exposes GLB only through configured HTTPS `BCA_PUBLIC_BASE_URL` and the controlled route.
- Public, reverse-proxy, or tailnet deployment requires Bambuddy authentication. Tailscale does not replace application identity.

### Files and 3MF

- Path joins use `safe_join_under` or explicit resolve/containment checks.
- Uploads validate content. BCA 3MF uploads are limited to 100 MB and validate ZIP members, compression ratio, decompressed size, duplicate members, and required files.
- A model 3MF must pass `.gcode.3mf` validation before native queue handoff.

### Billing and Providers

- Image, 3D, and multi-color stages require explicit human confirmation.
- Billed POSTs are never automatically retried.
- Non-healthy print analysis requires a separate acknowledgement and smoke must resume the same session.
- Do not copy real paid credentials or request/response bodies into public reports.

## Contributor checks

Security changes require negative-path tests for missing permissions, insufficient permissions, unsafe URLs, path escape, invalid state transition, or missing cache headers. See the [English engineering contract](AGENTS.md) and [English contribution guide](CONTRIBUTING.en.md).
