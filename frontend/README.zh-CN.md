# Bambuddy 前端

[English](README.md) | **中文**

Bambuddy 前端是 React + TypeScript + Vite 单页管理界面。构建产物进入仓库根目录 `static/`，由同一 FastAPI 应用提供；它不是独立部署的前端服务。

## 开发

在仓库根目录执行：

```powershell
npm --prefix .\frontend ci
npm --prefix .\frontend run lint
npm --prefix .\frontend run test:run
npm --prefix .\frontend run build
```

需要本地 API 时：

```powershell
$env:DATA_DIR = "$PWD\data"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
npm --prefix .\frontend run dev
```

### Linux Docker Compose 开发

在仓库根目录使用开发 Compose 栈，不要再分别启动前端和后端命令：

```bash
docker compose -f docker-compose.dev.yml up --build
```

这是仅用于开发的双服务例外：`frontend` 以 Vite HMR 运行在 `http://127.0.0.1:5173`，`backend` 以 Uvicorn reload 运行在 `http://127.0.0.1:8000`。Compose 设置 `BACKEND_HOST=backend` 和 `BACKEND_PORT=8000`，使 `/api` 与 `/api/v1/ws` 均通过 Docker 服务 DNS 代理；原生开发不设置这两个变量，仍代理到 `localhost:8000`。前端服务不是可独立部署的生产应用。

使用 `docker compose -f docker-compose.dev.yml down` 停止开发栈。Provider 环境注入和开发卷重置说明见仓库根 README。

## BCA 页面

| 路由 | 组件 | 用途 |
|---|---|---|
| `/creator` | `pages/CreatorPage.tsx` | Agent 对话、候选效果图、工作流画布、产物下载、校准与任务交接。 |
| `/tasks` | `pages/TaskListPage.tsx` | BCA 模型任务、切片文件附加、打印机选择与原生队列交接。 |
| `/creator/settings` | `pages/CreatorSettingsPage.tsx` | 明文 Provider 凭据、运行参数与热加载。 |

认证启用时，Creator 效果图必须通过带 Bearer token 的 Blob fetch 预览，不能把受控图片路由直接赋给 `<img src>`。effect 清理必须 abort 未完成请求并 revoke 已创建 Blob URL。

## 前后端契约

- BCA 导航必须保持在 `components/Layout.tsx` 的既有 Bambuddy Shell 中，不创建第二套应用外壳。
- 普通产物下载保持受控 BCA route；不要向前端暴露 Provider 临时 URL。
- BCA task 在 root 上传并验证 `.gcode.3mf` 前仍只是模型 3MF。
- `CreatorSettingsPage` 使用 `/api/v1/creator/config`：GET 需要 `SETTINGS_READ`，PUT 需要 `SETTINGS_UPDATE`，返回与保存的明文凭据响应必须为 `Cache-Control: private, no-store`。
- `CreatorPage` 卡片动作默认使用 POST；不要让确认、分析或生成动作退化成 GET/405。
- 修改 creator response 或 task response 时同步更新 `backend/app/services/creator_integration.py`、`creator.py`、`bca_tasks.py` 与前端 type/state。

## 相关文档

- [中文开发 README](../README.md)
- [English developer README](../README.en.md)
- [中文部署指南](../DEPLOYMENT_BCA.zh-CN.md)
- [English deployment guide](../DEPLOYMENT_BCA.md)
- [中文工程契约](../AGENTS.zh-CN.md)
- [English engineering contract](../AGENTS.md)
