# Documentation Audit / 文档审计


[中文](DOCUMENTATION_AUDIT.zh-CN.md) | **English**
**Scope / 范围**: Complete Markdown inventory for the BCA-integrated Bambuddy worktree. This records whether a document was updated for the BCA fork or intentionally retained as inherited upstream documentation. It is a scope record, not a replacement for the referenced document.

| Document | Status | Reason |
|---|---|---|
| `README.md` | Rewritten | Complete Chinese BCA developer README and public GitHub entry point; links to the English version. |
| `README.en.md` | Added | Complete English BCA developer README, one click from the root README. |
| `AGENTS.md` / `AGENTS.zh-CN.md` | Updated / Added | Paired English and Chinese BCA engineering contracts. |
| `BCA_ARCHITECTURE.md` / `BCA_ARCHITECTURE.zh-CN.md` | Updated / Added | Paired English and Chinese BCA architecture guides. |
| `DEPLOYMENT_BCA.md` / `DEPLOYMENT_BCA.zh-CN.md` | Updated / Added | Paired English and Chinese deployment, backup, plaintext configuration, and smoke guides. |
| `frontend/README.md` / `frontend/README.zh-CN.md` | Rewritten / Added | Paired frontend development guides replacing the Vite template. |
| `DOCUMENTATION_AUDIT.md` / `DOCUMENTATION_AUDIT.zh-CN.md` | Updated / Added | Paired exhaustive scope and inheritance records. |
| `.env.bca.example` | Updated | Initial runtime environment template; Agent Services can persist plaintext replacements. |
| `DOCKERHUB.md` / `DOCKERHUB.en.md` | Rewritten / Added | Paired BCA Compose/image guidance; removes upstream image pull instructions. |
| `SECURITY.md` / `SECURITY.en.md` | Rewritten / Added | Paired BCA security policy, plaintext configuration authorization, no-store, and reporting guidance. |
| `UPDATING.md` / `UPDATING.en.md` | Rewritten / Added | Paired BCA update/rollback procedure; removes upstream version and install URLs. |
| `CONTRIBUTING.md` / `CONTRIBUTING.en.md` | Rewritten / Added | Paired BCA contribution workflow; removes upstream repository/wiki/website PR requirements. |
| `install/README.md` / `install/README.en.md` | Rewritten / Added | Paired BCA installation-script scope and post-install setup. |
| `installers/windows/README.md` / `installers/windows/README.en.md` | Rewritten / Added | Paired BCA Windows installer-build guide. |
| `slicer-api/README.md` / `slicer-api/README.en.md` | Rewritten / Added | Paired BCA slicer-sidecar and task-handoff guide. |
| `spoolbuddy/README.md` / `spoolbuddy/README.en.md` | Rewritten / Added | Paired SpoolBuddy hardware/BCA inventory relationship guide. |
| `docs/spoolman-inventory-test-plan.md` / `.en.md` | Rewritten / Added | Paired BCA calibration inventory test plan. |
| `docs/storage-locations.md` / `.en.md` | Rewritten / Added | Paired BCA storage/database recovery guide. |
| `docs/onboarding-tour-plan.md` / `.en.md` | Rewritten / Added | Paired BCA administrator onboarding plan. |
| `docs/migration-vp-ftp-port.md` / `.en.md` | Rewritten / Added | Paired BCA Virtual Printer port migration guide. |
| `docs/bambu_lab_preset_sync_api.md` / `.en.md` | Rewritten / Added | Paired BCA preset/slicing integration guide. |
| `docs/authentication/entra-id.md` / `.en.md` | Rewritten / Added | Paired Entra permission impact guide for BCA. |
| `CHANGELOG.md` | Inherited | Historical upstream release ledger; not rewritten because it must preserve release history. |
| `CODE_OF_CONDUCT.md` | Inherited | Governance policy is unchanged. |
| `BACKERS.md` | Inherited | Attribution is unchanged. |

## Cross-document invariants / 跨文档不变量

- BCA does not automatically read source-project `.env` or `.env.local`; deployment environment values seed initial Provider configuration, while Agent Services persists plaintext Provider replacements in Bambuddy settings.
- Creator output is not directly printable: root must attach a validated sliced `.gcode.3mf` before native queue handoff.

- Billed providers require explicit confirmation. Non-healthy Meshy analysis requires a separate acknowledgement and same-session resume.
- The embedded app is single-process until distributed locks, durable worker recovery, and ownership filtering are deliberately implemented.

## Link audit exception / 链接审计例外

`CHANGELOG.md` retains one historical relative link to removed `backend/app/services/background_dispatch.py`. It is intentionally retained as a release-history reference. The complete project audit covers 82 Markdown files, with no unbalanced code fences and no other broken relative links.
