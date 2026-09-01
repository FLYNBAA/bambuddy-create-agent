# BCA Microsoft Entra ID 认证

[English](entra-id.en.md) | **中文**

Microsoft Entra ID 属于 Bambuddy 原生认证层。BCA 不实现第二套 OIDC；Creator、Tasks、Agent Services 继承 Bambuddy 用户与权限。

## BCA 权限影响

| BCA 接口 | Bambuddy 权限 |
|---|---|
| 读取 `/api/v1/creator/config` 明文配置 | `SETTINGS_UPDATE` |
| 保存并热加载 Creator 配置 | `SETTINGS_UPDATE` |
| 操作 creator 直接工作流与推送订单 | `QUEUE_CREATE` |
| 下载 creator 产物 | `QUEUE_READ_ALL` |
| 创建/附加 BCA task | `LIBRARY_UPLOAD` / `QUEUE_CREATE` |
| 删除 BCA task | `QUEUE_DELETE_ALL` |

Entra 用户、group、role 与 API Key 的映射必须在 Bambuddy 原生认证中配置。不要仅依赖网络代理、Tailscale 或 Creator 页面隐藏来保护明文 Provider 配置。

## 部署检查

1. 反向代理提供 HTTPS。
2. Entra 回调 URL 指向当前 BCA/Bambuddy fork 的公开 origin。
3. 管理员具有 `SETTINGS_READ` 与 `SETTINGS_UPDATE` 才能读取或写入 `/creator/settings` 明文值。
4. 使用普通用户验证其无法读取 Agent Services 配置。
5. 验证 `/api/v1/creator/config` 返回 `Cache-Control: private, no-store`。

参见 [中文安全策略](../../SECURITY.md) 与 [中文部署指南](../../DEPLOYMENT_BCA.zh-CN.md)。
