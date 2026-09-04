# BCA 安全策略

[English](SECURITY.en.md) | **中文**

本策略适用于 `bambuddy-create-agent`。安全问题应通过当前 BCA fork 的私有维护渠道报告；不要在公开 issue、截图、日志或文档中粘贴真实 Provider 凭据、打印机访问码、数据库备份或产物 URL。

## 报告内容

请包含：

- 漏洞描述与影响范围；
- 可复现步骤与最小 PoC；
- 受影响的 BCA/Bambuddy 版本和部署方式；
- 是否需要认证、特定权限、网络位置或数据库访问；
- 建议修复方案（如有）。

## BCA 安全边界

### 路由与权限

- 认证与权限采用 Bambuddy 原生模型。
- `/api/v1/creator/config` 的明文 GET 与热加载 PUT 都需要 `SETTINGS_UPDATE`；只读状态/API Key 不得读取 Provider 密钥。
- Creator 普通浏览器产物下载要求权限。Meshy `public_url` 使用独立不可猜测 Provider capability token；它不是 session ID，也不会出现在快照或 WebSocket 事件中。
- 新路由必须有显式 auth dependency，或在公共路由 allowlist 中注明理由。

### 明文 Provider 配置

当前产品允许网页、API 与 Bambuddy 数据库存储明文 Provider 值：

```text
DeepSeek API Key
Image API Key
Tencent Secret ID / Secret Key
Meshy API Key
```

安全边界不等于保密存储：拥有 `SETTINGS_READ`、数据库读取权或数据库备份的人可读取值。为降低缓存泄露风险，config GET/PUT 响应必须设置：

```text
Cache-Control: private, no-store
```

禁止将凭据写入普通会话快照、task、Provider 错误、日志、测试 fixture、公开文档或未受控客户端。

### 网络与下载

- Provider Base URL 必须经过 LAN-service HTTP(S) URL 安全检查；危险 scheme、metadata endpoint、数值编码 IP 等必须拒绝。
- 用户和 Provider URL 下载必须保持域名/重定向/路径安全边界。
- `MESHY_MODEL_INPUT_MODE=public_url` 使用配置的 HTTPS `BCA_PUBLIC_BASE_URL` 和独立不可猜测的 Provider capability token。这类能力 URL 只供 Meshy 使用，绝不返回浏览器或普通会话客户端。

### 文件与 3MF

- 路径拼接使用 `safe_join_under` 或显式 resolve/containment 检查。
- 上传必须验证内容；BCA 3MF 上传限制 512 MiB 并检查 ZIP 成员、压缩比、解压大小、重复成员和必需文件。多色校准与校色接受压缩/源 3MF 包，共用该 512 MiB 包契约和单槽 429 守卫。
- 模型 3MF 必须经过 `.gcode.3mf` 验证后才能进入原生打印队列。

### 付费与 Provider

- 产品 UI 没有计费确认门或问题确认门。付费 POST 绝不自动重试；遇到含糊网络结果时调用方必须查询会话状态。
- `brief/prepare` 始终自动补全并返回最终提示词，`image_prompt_ready` 对接受的输入为 true；不存在追问缺项或类型选择的路径，兼容字段 `questions` 保留且恒为空列表。提示词语言跟随调用方源语言。
- 多色校准只读取符合条件的活动 `spool` 行，不读取 `color_catalog`；成功映射需要非空 `assignments` 和最终产物。
- 不要把真实付费凭据或请求/响应复制到公开报告。

## 贡献者检查

安全相关修改必须包含负路径测试：无权限、权限不足、不安全 URL、路径逃逸、状态越权或缓存头缺失。详情见 [中文工程契约](AGENTS.zh-CN.md) 与 [中文贡献指南](CONTRIBUTING.md)。
