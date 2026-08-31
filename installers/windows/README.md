# BCA Windows 安装包构建

[English](README.en.md) | **中文**

此目录构建 BCA 的 Windows `.exe` 安装包。安装包必须从当前 `bambuddy-create-agent` 工作树构建，不能从 upstream Bambuddy 预构建包获得 BCA 功能。

## 安装包架构

```text
安装目录：C:\Program Files\Bambuddy\
数据目录：C:\ProgramData\Bambuddy\data\
日志目录：C:\ProgramData\Bambuddy\logs\
服务：NSSM 管理的 FastAPI/Uvicorn
浏览器入口：http://localhost:8000
```

BCA 产物随 `DATA_DIR` 保存：

```text
bca-agent/   creator session 与产物
bca-tasks/   等待切片的 task 源文件
```

Provider 明文配置保存于 Bambuddy 原生数据库 `bca_creator_*` settings；卸载、更新、迁移或备份时必须连同数据库与 data 一起处理。

## 构建前提

- Windows 10/11 x64 或 GitHub Windows runner；
- Python 3.11+；
- Node.js 22 LTS 与 npm；
- Inno Setup 6；
- 当前 BCA fork 工作树；
- 已安装 BCA Python 依赖与前端依赖。

## 构建步骤

从仓库根目录：

```cmd
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
cd installers\windows
python build.py
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" bambuddy.iss
```

输出：

```text
installers\windows\build\output\bambuddy-windows-setup.exe
```

## 安装后检查

1. 打开 `http://localhost:8000` 并完成管理员 Setup。
2. 在 `/creator/settings` 填入或确认 Provider 明文配置。
3. 检查 `/health`。
4. 按 Windows 网络限制手动使用 LAN IP 添加打印机。
5. 不要通过安装程序自动触发付费 Provider；需要时按部署指南使用明确批准 smoke。

## Windows 限制

- Virtual Printer 的 322/990/8883 等端口会触发 Firewall 规则。
- SSDP 自动发现和 Docker bridge 不是同一网络模型；Docker Desktop 见 [中文部署指南](../../DEPLOYMENT_BCA.zh-CN.md)。
- 数据恢复必须同时恢复原生数据库、`DATA_DIR` 和 `bca_creator_*` 配置。

## 相关文档

- [中文部署指南](../../DEPLOYMENT_BCA.zh-CN.md)
- [中文更新指南](../../UPDATING.md)
- [中文工程契约](../../AGENTS.zh-CN.md)
