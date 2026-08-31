# BCA Virtual Printer FTP 端口迁移

[English](migration-vp-ftp-port.en.md) | **中文**

Virtual Printer 属于 Bambuddy 原生功能，但 BCA task 最终会交给原生队列，因此端口迁移会影响 BCA 完整打印链路。

## 网络模型

- Linux host networking：Virtual Printer 可直接绑定所需端口。
- Windows Docker Desktop bridge：需显式映射控制、MQTT、被动 FTP 与可选相机端口；默认 BCA smoke override 只发布 Web `8012:8000`，不等于完整 Virtual Printer 支持。

## 迁移步骤

1. 在变更端口前备份数据库、`DATA_DIR` 和 `bca_creator_*` 配置。
2. 停止原生/容器服务。
3. 更新 Compose 或 Virtual Printer 配置，确保宿主端口不冲突。
4. 对 bridge 模式映射所需 FTP passive 范围；非 proxy VP 每实例需要端口 slice，proxy VP 可能需要完整 printer passive 范围。
5. 启动并检查 `/health`。
6. 使用非付费的已切片 `.gcode.3mf` 验证原生队列上传、确认和取消。

## BCA 关系

BCA 不直接 FTP 上传模型 3MF。Creator → task → root 切片 → 原生 Queue 的末端由 Virtual Printer/原生 FTPS 接管。不要为 BCA 增加第二套 FTP 服务。

参见 [中文部署指南](../DEPLOYMENT_BCA.zh-CN.md)。
