# 文档审计

[English](DOCUMENTATION_AUDIT.md) | **中文**

本文记录 BCA 二次开发工作树中的开发者 Markdown 文档范围、语言版本与继承决策。它不替代被引用文档。

## BCA 开发者文档语言对照

| 中文 | English | 用途 |
|---|---|---|
| [README.md](README.md) | [README.en.md](README.en.md) | GitHub 默认开发者入口、工作流、配置、备份、部署和验证。 |
| [AGENTS.zh-CN.md](AGENTS.zh-CN.md) | [AGENTS.md](AGENTS.md) | 工程契约、状态机、代码修改与验证约束。 |
| [BCA_ARCHITECTURE.zh-CN.md](BCA_ARCHITECTURE.zh-CN.md) | [BCA_ARCHITECTURE.md](BCA_ARCHITECTURE.md) | 模块边界、数据流、Provider 与持久化架构。 |
| [DEPLOYMENT_BCA.zh-CN.md](DEPLOYMENT_BCA.zh-CN.md) | [DEPLOYMENT_BCA.md](DEPLOYMENT_BCA.md) | Windows、Linux、Docker、代理、备份和付费 smoke 部署指南。 |
| [frontend/README.zh-CN.md](frontend/README.zh-CN.md) | [frontend/README.md](frontend/README.md) | 前端开发、BCA 页面与 API 契约。 |
| [UPDATING.md](UPDATING.md) | [UPDATING.en.md](UPDATING.en.md) | BCA 更新、回滚与恢复。 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | [CONTRIBUTING.en.md](CONTRIBUTING.en.md) | BCA fork 贡献流程。 |
| [SECURITY.md](SECURITY.md) | [SECURITY.en.md](SECURITY.en.md) | BCA 权限、明文配置与安全报告。 |
| [DOCKERHUB.md](DOCKERHUB.md) | [DOCKERHUB.en.md](DOCKERHUB.en.md) | Compose/镜像运行说明。 |
| [install/README.md](install/README.md) | [install/README.en.md](install/README.en.md) | 安装脚本范围与 BCA 安装后设置。 |
| [installers/windows/README.md](installers/windows/README.md) | [installers/windows/README.en.md](installers/windows/README.en.md) | Windows 安装包构建。 |
| [slicer-api/README.md](slicer-api/README.md) | [slicer-api/README.en.md](slicer-api/README.en.md) | 可选 slicer sidecar。 |
| [spoolbuddy/README.md](spoolbuddy/README.md) | [spoolbuddy/README.en.md](spoolbuddy/README.en.md) | 硬件开发与 BCA 耗材关系。 |
| [docs/*.md](docs/) | 对应 `.en.md` | BCA 相关耗材、存储、引导、FTP、预设与 Entra 技术说明。 |

## 已更新与配对文档

所有面向 BCA 开发、部署、安装、贡献、安全、slicer、SpoolBuddy 与 `docs/` 技术说明的当前默认中文文件均有对应 `.en.md` 英文文件，并在首行相互链接。

未改写为双语对的是历史或治理记录：

```text
CHANGELOG.md
CODE_OF_CONDUCT.md
BACKERS.md
```

它们不定义 BCA 部署、开发、安装或运行流程。

## 跨文档不变量

- BCA 不读取 source-project `.env` / `.env.local`；环境变量给出首次启动值，Agent Services 可把明文 Provider 值持久化到 Bambuddy settings。
- `/api/v1/creator/config` 的明文读取需要 `SETTINGS_READ`，写入与热加载需要 `SETTINGS_UPDATE`，响应为 `Cache-Control: private, no-store`。
- BCA 模型 3MF 不能绕过 `.gcode.3mf` 验证直接排队。
- 图像、3D 与多色阶段均保持明确确认门；非 `healthy` Meshy 分析需要同 session 问题确认后恢复。
- 当前 BCA 是单进程模型，不允许用多 Uvicorn worker 声称支持分布式并发。

## 审计例外

`CHANGELOG.md` 保留了指向已删除 `backend/app/services/background_dispatch.py` 的历史链接，用于表达历史发布内容。完整项目审计覆盖 82 个 Markdown 文件，没有未闭合代码 fence，除该历史链接外没有其他损坏相对链接。
