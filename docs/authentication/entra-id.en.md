# BCA Microsoft Entra ID Authentication

[中文](entra-id.md) | **English**

Microsoft Entra ID is a native Bambuddy authentication layer. BCA does not implement a second OIDC system: Creator, Tasks, and Agent Services inherit Bambuddy users and permissions.

## BCA permission impact

| BCA interface | Bambuddy permission |
|---|---|
| Read plaintext `/api/v1/creator/config` | `SETTINGS_UPDATE` |
| Save and hot-reload Creator configuration | `SETTINGS_UPDATE` |
| Operate the direct creator workflow and submit orders | `QUEUE_CREATE` |
| Download creator artifacts | `QUEUE_READ_ALL` |
| Create/attach BCA tasks | `LIBRARY_UPLOAD` / `QUEUE_CREATE` |
| Delete BCA tasks | `QUEUE_DELETE_ALL` |

Configure Entra users, groups, roles, and API keys through native Bambuddy authentication. Do not rely only on a network proxy, Tailscale, or hidden Creator navigation to protect plaintext Provider configuration.

## Deployment checks

1. Reverse proxy provides HTTPS.
2. Entra callback URL targets the current BCA/Bambuddy fork public origin.
3. Administrators have `SETTINGS_READ` and `SETTINGS_UPDATE` to read/write `/creator/settings` plaintext values.
4. Verify an ordinary user cannot read Agent Services configuration.
5. Verify `/api/v1/creator/config` returns `Cache-Control: private, no-store`.

See the [English security policy](../../SECURITY.en.md) and [English deployment guide](../../DEPLOYMENT_BCA.md).
