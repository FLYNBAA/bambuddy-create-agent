# Documentation Audit / 文档审计

**Scope / 范围**: Complete Markdown inventory for the BCA-integrated Bambuddy worktree. This records whether a document was updated for the BCA fork or intentionally retained as inherited upstream documentation. It is a scope record, not a replacement for the referenced document.

| Document | Status | Reason |
|---|---|---|
| `README.md` | Rewritten | Complete Chinese BCA developer README and public GitHub entry point; links to the English version. |
| `README.en.md` | Added | Complete English BCA developer README, one click from the root README. |
| `DOCUMENTATION_AUDIT.md` | Added | Exhaustive scope and inheritance record for this BCA documentation pass. |
| `AGENTS.md` | Updated | Engineering contract for BCA gates, storage, queue handoff, deployment, and verification. |
| `BCA_ARCHITECTURE.md` | Updated | Current BCA ownership boundaries, state invariants, authenticated previews, recovery, and public Meshy route. |
| `DEPLOYMENT_BCA.md` | Updated | Windows/Linux deployment, public route, secret injection, and paid smoke recovery policy. |
| `.env.bca.example` | Updated | Redacted BCA Provider variable-name template. |
| `DOCKERHUB.md` | Updated | Removes historic beta pull claim; references current versioned image guidance. |
| `CHANGELOG.md` | Inherited | Historical upstream release ledger; not rewritten because it must preserve release history. |
| `SECURITY.md` | Inherited | Repository-wide security policy remains authoritative; BCA follows it. |
| `UPDATING.md` | Inherited | General Bambuddy update procedure remains valid; BCA is built in the same image. |
| `CONTRIBUTING.md` | Inherited | Repository contribution process remains valid. |
| `CODE_OF_CONDUCT.md` | Inherited | Governance policy is unchanged. |
| `BACKERS.md` | Inherited | Attribution is unchanged. |
| `spoolbuddy/README.md` | Inherited | Raspberry Pi hardware wiring is independent of BCA. |
| `slicer-api/README.md` | Inherited | Optional slicer sidecar contract is unchanged; BCA still requires root-supplied sliced output. |
| `install/README.md` | Inherited | Native installer reference is unchanged. |
| `installers/windows/README.md` | Inherited | Windows installer instructions are unchanged. |
| `frontend/README.md` | Rewritten | Replaces the Vite template with Bambuddy frontend and BCA surface guidance. |
| `docs/spoolman-inventory-test-plan.md` | Inherited | Spoolman test plan remains separate; BCA consumes native active spool inventory. |
| `docs/storage-locations.md` | Inherited | Storage-location reference remains valid; BCA-specific data paths are documented in deployment/BCA docs. |
| `docs/onboarding-tour-plan.md` | Inherited | Existing Bambuddy onboarding plan is unchanged. |
| `docs/migration-vp-ftp-port.md` | Inherited | Virtual-printer migration reference is unchanged. |
| `docs/bambu_lab_preset_sync_api.md` | Inherited | Bambu preset-sync API reference is unchanged. |
| `docs/authentication/entra-id.md` | Inherited | Entra ID setup remains native Bambuddy authentication documentation. |

## Cross-document invariants / 跨文档不变量

- BCA never automatically reads source-project `.env` or `.env.local`; Provider secrets are deployment environment or secret-manager inputs.
- Creator output is not directly printable: root must attach a validated sliced `.gcode.3mf` before native queue handoff.

- Billed providers require explicit confirmation. Non-healthy Meshy analysis requires a separate acknowledgement and same-session resume.
- The embedded app is single-process until distributed locks, durable worker recovery, and ownership filtering are deliberately implemented.

## Link audit exception / 链接审计例外

`CHANGELOG.md` retains one historical relative link to removed `backend/app/services/background_dispatch.py`. It is intentionally retained as a release-history reference; current operator and BCA documents contain no broken relative links. All audited Markdown fences are balanced.
