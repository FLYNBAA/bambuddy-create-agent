# BCA Slicer-API 侧车

[English](README.en.md) | **中文**

可选的 Slicer-API 侧车为 OrcaSlicer 或 Bambu Studio CLI 提供 HTTP 包装。BCA 不强制使用它：BCA task 必须由 root 上传最终通过验证的 `.gcode.3mf`，这个文件可以由该侧车、桌面 slicer 或其他兼容流程生成。

## 使用场景

```text
模型 3MF / STL
  → 可选 slicer sidecar 或桌面 slicer
  → .gcode.3mf
  → root 上传到 /tasks
  → BCA 验证 Metadata/plate_N.gcode + Metadata/slice_info.config
  → 原生 Bambuddy queue
```

## 启动

从本目录：

```bash
docker compose up -d
curl http://localhost:3003/health
```

同时启动 Bambu Studio profile：

```bash
docker compose --profile bambu up -d
curl http://localhost:3001/health
curl http://localhost:3003/health
```

默认端口：

| 服务 | 端口 |
|---|---|
| OrcaSlicer API | `3003` |
| Bambu Studio API | `3001` |

在 Bambuddy Settings → Slicer 启用 Slicer API 并填写 Sidecar URL。BCA 后台不会自动将未验证模型 3MF 直接交给打印机。

## 网络和架构

- 镜像通常为 `linux/amd64`；ARM64 主机可使用独立 x86_64 sidecar 主机或经仿真运行。
- sidecar 可以与 Bambuddy 不在同一主机；填写可到达 URL。
- 生产反向代理、认证与 Provider 明文配置不由 sidecar 管理，仍由 BCA/Bambuddy 管理。
- sidecar 产生的文件仍必须经过 BCA task 的切片验证。

## 相关文档

- [中文部署指南](../DEPLOYMENT_BCA.zh-CN.md)
- [中文 README](../README.md)
- [English Slicer-API guide](README.en.md)
