# Contributing to BCA

[中文](CONTRIBUTING.md) | **English**

This repository is the Bambuddy Create Agent (BCA) fork. Contributions target this BCA fork, not upstream `maziggy/bambuddy` repositories, Wiki, website, or PR workflow.

## Before you start

1. Describe the scope through the current BCA fork's issue, discussion, or maintainer-designated channel.
2. Determine whether it affects payment gates, state machine behavior, Providers, persistence, queue handoff, permissions, plaintext configuration, or deployment documentation.
3. Record architecture choices in the issue/PR rather than creating a competing convention.
4. Never commit real Provider credentials, production databases, artifact URLs, or printer access codes.

## Clone and development environment

```bash
git clone <your-bca-fork-url> bambuddy-create-agent
cd bambuddy-create-agent
python -m venv .venv
```

Linux/macOS:

```bash
.venv/bin/python -m pip install -r requirements.txt
npm --prefix frontend ci
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
npm --prefix .\frontend ci
```

Use an isolated data directory:

```powershell
$env:DATA_DIR = "$PWD\data"
```

Do not let tests or local development read source-project `.env` / `.env.local`.

## Code boundaries

- Bambuddy owns printers, Library, native queueing, authentication, API keys, WebSockets, deployment, and transport.
- BCA owns creator sessions, Provider orchestration, artifacts, calibration, and BCA tasks.
- Do not duplicate native queue, printer, authentication, or file state machines.
- Implement Providers behind existing Protocols and `factory.py`; do not leak provider-specific types into `service.py`.
- External routes continue to use Bambuddy permission dependencies.

## Plaintext Provider configuration changes

The current product allows Agent Services to persist plaintext Provider credentials. Changes to `/api/v1/creator/config` must preserve:

```text
GET → SETTINGS_READ
PUT → SETTINGS_UPDATE
Cache-Control: private, no-store
```

Update together:

```text
creator.py
creator_integration.py
CreatorSettingsPage.tsx
README.md / README.en.md
DEPLOYMENT_BCA.md / DEPLOYMENT_BCA.zh-CN.md
tests
```

Do not write credentials to ordinary creator snapshots, tasks, logs, public download routes, or test fixtures.

## Payment and state-machine changes

- Image, 3D, and Meshy multi-color calls require explicit confirmation.
- Billed POSTs are never automatically retried.
- A non-`healthy` analysis requires a separate issue acknowledgement; full smoke must resume the same session instead of rerunning image/3D work.
- New states update contracts, service, API, frontend, tests, and documents together.
- Cancellation persists failure state before re-raising `CancelledError`.

## Frontend changes

- Use the existing `Layout.tsx` and design tokens; do not create a second shell or color system.
- Keep `/creator`, `/tasks`, and `/creator/settings` API types synchronized with backend responses.
- Authenticated image previews must use Bearer-authenticated Blob fetch and abort/revoke during effect cleanup.
- Creator card actions must POST.
- BCA developer copy must be updated in both language versions with first-line language switches.

## Verification

Minimum verification:

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_creator_config_api.py -q
.\.venv\Scripts\ruff.exe check backend\app backend\tests
npm --prefix .\frontend run lint
npm --prefix .\frontend run test:run
npm --prefix .\frontend run build
```

For broad changes:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Run paid Provider smoke only after explicit user approval. Verify Docker changes on a Docker host and UI changes in a browser at desktop and 390px width.

## Pull request checklist

- Describe BCA behavior, boundaries, and failure semantics.
- List tests, builds, browser checks, and Docker checks performed.
- State whether a billed Provider call occurred; do not call one without approval.
- Update paired Chinese and English developer documents.
- Describe persistence, migration, backup-contract, and rollback impact.
- Do not make upstream Wiki/website PRs a BCA completion condition; repository BCA documents are authoritative for this fork.

## References

- [English engineering contract](AGENTS.md)
- [English architecture](BCA_ARCHITECTURE.md)
- [English deployment guide](DEPLOYMENT_BCA.md)
- [Documentation audit](DOCUMENTATION_AUDIT.md)
