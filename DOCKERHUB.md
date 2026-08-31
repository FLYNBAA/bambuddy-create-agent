# BCA Docker 镜像与 Compose

[English](DOCKERHUB.en.md) | **中文**

BCA 是从当前 `bambuddy-create-agent` 工作树构建的 Bambuddy 二次开发版本。不要拉取 upstream `maziggy/bambuddy` 公共镜像并期望获得 BCA 创作、校准、任务和明文配置功能。

## 推荐运行

Linux：

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f bambuddy
```

Windows Docker Desktop：

```powershell
docker compose -f .\docker-compose.yml -f .\docker-compose.windows.yml up -d --build
curl http://127.0.0.1:8012/health
```

普通停止：

```bash
docker compose down
```

不要对存在数据的环境使用 `down -v`；它会删除命名数据卷。

## 容器数据

```text
/app/data  数据库或 data layout、BCA 会话、3MF、任务和归档
/app/logs  应用日志
```

若使用外部 PostgreSQL，数据库不在 `/app/data`；备份必须同时包括 PostgreSQL dump、`DATA_DIR` 和数据库中的 `bca_creator_*` 明文 Provider 配置。

## 网络

Linux 默认 host networking。Windows Docker Desktop 使用 bridge override，必须手工使用 LAN IP 添加打印机，并为 Virtual Printer/被动 FTP 等能力按需要映射额外端口。

完整 BCA 部署、反向代理、明文配置、备份与 smoke 策略见 [中文部署指南](DEPLOYMENT_BCA.zh-CN.md)。
