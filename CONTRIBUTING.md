# 贡献 BCA

[English](CONTRIBUTING.en.md) | **中文**

本仓库是 Bambuddy Create Agent（BCA）二次开发仓库。贡献必须针对当前 BCA fork，而不是 upstream `maziggy/bambuddy` 的仓库、Wiki、网站或 PR 流程。

## 开始前

1. 在当前 BCA fork 的 issue、讨论区或维护者指定渠道说明工作范围。
2. 先确认是否会影响付费确认门、状态机、Provider、持久化、队列、权限、明文配置或部署文档。
3. 将架构选择写入 issue/PR，避免同时创建第二套约定。
4. 不要把真实 Provider 凭据、生产数据库、产物 URL 或打印机访问码提交到分支、测试或 PR。

## 克隆与开发环境

```bash
git clone <your-bca-fork-url> bambuddy-create-agent
cd bambuddy-create-agent
python -m venv .venv
```

Linux/macOS：

```bash
.venv/bin/python -m pip install -r requirements.txt
npm --prefix frontend ci
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
npm --prefix .\frontend ci
```

使用隔离数据目录：

```powershell
$env:DATA_DIR = "$PWD\data"
```

不要让测试或本地开发读取 source-project `.env` / `.env.local`。

## 代码边界

- Bambuddy 负责打印机、Library、原生队列、认证、API Key、WebSocket、部署和传输。
- BCA 负责创作会话、Provider 编排、产物、校准和 BCA task。
- 不要复制原生 queue、printer、auth 或文件状态机。
- Provider 通过现有 Protocol 与 `factory.py` 组合，不能让供应商类型泄漏到 `service.py`。
- 外部可访问接口继续使用 Bambuddy 权限依赖。

## 明文 Provider 配置改动

当前产品允许 Agent Services 持久化明文 Provider 凭据。涉及 `/api/v1/creator/config` 时必须保持：

```text
GET → SETTINGS_READ
PUT → SETTINGS_UPDATE
Cache-Control: private, no-store
```

同时更新：

```text
creator.py
creator_integration.py
CreatorSettingsPage.tsx
README.md / README.en.md
DEPLOYMENT_BCA.md / DEPLOYMENT_BCA.zh-CN.md
测试
```

不要把凭据写到普通 creator snapshot、task、日志、公共下载路由或测试 fixture。

## 付费和状态机改动

- 图像、3D 与 Meshy 多色请求需要明确确认。
- 付费 POST 不得自动重试。
- 非 `healthy` 分析必须有独立问题确认；full smoke 应恢复同一 session，不能重跑图像/3D。
- 新状态同步更新 contracts、service、API、frontend、测试和文档。
- 取消必须持久化失败状态再抛出 `CancelledError`。

## 前端改动

- 使用现有 `Layout.tsx` 和 design tokens，不创建第二套 Shell/颜色语义。
- `/creator`、`/tasks`、`/creator/settings` 的 API 类型与后端 response 同步。
- 认证状态下图片预览必须带 Bearer token Blob fetch，并在 effect cleanup 中 abort/revoke。
- Creator 卡片动作必须 POST。
- BCA 文案与开发者文档必须同步中英文版本并保持首行语言互链。

## 验证

最低验证：

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_creator_config_api.py -q
.\.venv\Scripts\ruff.exe check backend\app backend\tests
npm --prefix .\frontend run lint
npm --prefix .\frontend run test:run
npm --prefix .\frontend run build
```

变更影响更广时运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

付费 Provider 只可在明确用户批准后使用 smoke runner。Docker 变更必须在 Docker 主机验证。UI 变更必须用浏览器验证桌面与 390px 宽度。

## PR 清单

- 清楚描述 BCA 行为、边界和失败语义。
- 列出执行的测试、构建、浏览器或 Docker 验证。
- 说明是否发生付费 Provider 调用；未批准时不得调用。
- 更新中英文配对开发者文档。
- 对持久化字段、迁移、备份契约和回滚影响作出说明。
- 不链接 upstream Wiki/website PR 作为 BCA 完成条件；本文档和仓库内 BCA 文档是当前 fork 的权威开发文档。

## 相关文档

- [中文工程契约](AGENTS.zh-CN.md)
- [中文架构说明](BCA_ARCHITECTURE.zh-CN.md)
- [中文部署指南](DEPLOYMENT_BCA.zh-CN.md)
- [文档审计](DOCUMENTATION_AUDIT.zh-CN.md)
