# BCA 存储位置与数据布局

[English](storage-locations.en.md) | **中文**

BCA 使用 Bambuddy `DATA_DIR` 与原生数据库。部署与迁移时不要只移动其中一部分。

```text
DATA_DIR/
├─ bca-agent/       creator session SQLite、上传图、概念图、GLB、3MF
├─ bca-tasks/       等待 root 切片的模型 3MF
├─ archive/         Bambuddy archive 与 Library 相关数据
├─ sessions.sqlite3 / 原生数据库（SQLite 部署时依配置）
└─ virtual_printer/ Virtual Printer 数据
```

数据库还保存：

```text
bca_tasks
bca_creator_*
```

`bca_creator_*` 包含明文 Provider 配置。SQLite 必须连同一致的 WAL sidecar 备份；PostgreSQL 必须 dump `DATABASE_URL` 对应数据库。任何恢复都必须把数据库与 `DATA_DIR` 的匹配快照一起恢复。

文件系统路径不应通过 API 返回。Creator 产物由受控路由下载；Meshy public URL 仅用受控 GLB capability route。

参见 [中文部署指南](../DEPLOYMENT_BCA.zh-CN.md)。
