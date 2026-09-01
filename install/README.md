# BCA 安装脚本说明

[English](README.en.md) | **中文**

此目录的脚本来自 Bambuddy 安装基础。BCA 部署应使用当前 BCA fork 工作树、当前 BCA Compose 文件和仓库内开发/部署文档；不要下载 upstream `maziggy/bambuddy` 的安装脚本并期待获得 BCA 功能。

## 推荐安装方式

### Linux Docker

在 BCA fork 工作树中：

```bash
docker compose --env-file .env.bca up -d --build
```

生产 Linux 默认 host networking，支持发现、Virtual Printer、相机和 LAN 协议。

### Windows Docker Desktop

```powershell
docker compose --env-file .env.bca -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d --build
curl http://127.0.0.1:8012/health
```

Windows bridge 模式通过 `.env.bca` 的 `BCA_DISCOVERY_SUBNETS` 单播扫描明确的打印机 LAN CIDR，也可按 LAN IP 添加。正常停止：

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml down
```

不要对保留数据的部署使用 `down -v`。

### 本地 Python 开发/测试

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
npm --prefix .\frontend ci
npm --prefix .\frontend run build
$env:DATA_DIR = "$PWD\data"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

## 当前脚本范围

| 脚本 | 原生职责 | BCA 使用说明 |
|---|---|---|
| `install.sh` | Linux/macOS 原生 Bambuddy 安装 | 只有在本 BCA fork 工作树中运行并验证 BCA 依赖与静态构建后使用。 |
| `docker-install.sh` | Linux/macOS Docker 引导 | 不下载 upstream compose；使用当前 fork 的 `docker-compose.yml`。 |
| `docker-install.ps1` | Windows Docker Desktop 引导 | BCA 需要同时使用 `docker-compose.windows.yml` override。 |
| `windows-installer.ps1` | 原生 Windows 服务安装 | 需要 BCA fork、BCA 依赖和当前前端构建；详见仓库根部署指南。 |
| `update.sh` | systemd 原生更新 | 更新前备份原生数据库与 `DATA_DIR`，详见 [更新指南](../UPDATING.md)。 |

## BCA 安装后配置

1. 完成 Bambuddy Setup，建立受控管理员访问。
2. 在 `/creator/settings` 填入或确认 Provider 参数和明文凭据。
3. 记录这些配置会写入 Bambuddy 数据库的 `bca_creator_*`。
4. 添加打印机与耗材。
5. 在 `/creator` 按直接工作流卡片完成创意、风格图、3D 概念图、打印校准、打印分析与订单推送；产品 UI 没有付费确认门。
6. 在 `/tasks` 上传 root 切片后的 `.gcode.3mf`，再交给原生队列。

BCA 安装、网络、反向代理、备份、PostgreSQL 和付费 smoke 的完整说明见 [中文部署指南](../DEPLOYMENT_BCA.zh-CN.md)。
