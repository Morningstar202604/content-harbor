# 外部成熟工具集成策略

> 原则：**不重复造轮子**——优先复用开源生态，自研只做胶水层和兜底。

## 已接入工具

| 工具 | 用途 | 安装方式 | 复用平台 |
|------|------|----------|----------|
| **web-publish** (MIT) | 掘金 Draft API 客户端 | `uv pip install git+https://github.com/PsChina/web-publish.git` | 掘金草稿创建 |
| **patchright** | 反检测 Playwright fork | `uv pip install patchright` | 所有需要浏览器的平台 |
| **xmlrpc.client** (stdlib) | MetaWeblog XML-RPC | 标准库 | 博客园 |

## 各平台集成策略

### 博客园（cnblogs）—— 纯 API，零浏览器

- **方案**：MetaWeblog XML-RPC API（Python 标准库 `xmlrpc.client`）
- **工具**：`service/publishing/tools/metaweblog.py`
- **状态**：已在 `CnblogsAdapter` 中完整实现（发布/更新/删除/列表/图片上传）
- **优势**：不需要浏览器、不需要模拟登录、Token 长期有效

### 掘金（juejin）—— API Draft + UI 兜底发布

- **Draft API**：`POST /content_api/v1/article_draft/create` + `/update`
  - web-publish 已封装 → `JuejinClient.create_draft()` / `update_draft()`
  - 只需 Cookie + UUID（从浏览器 DevTools 取一次即可）
- **Publish API 已封**（2026-09 实测）→ 走浏览器 UI 自动点"确定并发布"
- **工具**：`service/publishing/tools/juejin_api.py`（Draft 操作）+ `JuejinAdapter`（UI 兜底）

### 知乎（zhihu）—— 浏览器自动化

- **无公开发布 API**（官方 GitHub 8 月刚发 `ZhihuPublisher` 和 `zhihu-mediacloud-uploader`，仍在早期）
- **方案**：Patchright（反检测 Playwright）+ cookie 持久化
- **工具**：`ZhihuAdapter`（Patchright 浏览器）+ 可择机接入知乎官方 SDK

### B站（bilibili）—— 浏览器自动化

- **无公开稳定 API**（bilibili-api 已被 DMCA 下架）
- **方案**：biliup-rs (Rust) 做视频投稿 + Patchright 做专栏发布
- **工具**：`BilibiliAdapter`（Patchright 浏览器）

### CSDN / 思否（SegmentFault）—— 浏览器自动化

- **无公开 API**
- **方案**：Patchright + DOM 操作 + 回读验证（verify-after-act）
- **工具**：`CsdnAdapter` / `SegmentFaultAdapter`

### 头条（Toutiao）—— 浏览器自动化 + JS 签名

- **需要 JS `_signature` 参数**（纯 HTTP 调不通）
- **方案**：Patchright 浏览器自动化（JS 签名在页面上下文中自动算）
- **参考**：`super-publisher` (ClawHub) 已验证方案可行

### 微信公众号 —— 草稿箱 API

- **有官方草稿箱 API**（AppID + Secret）
- **工具**：`wenyan-cli` + `wenyan-mcp` 最成熟（排版 + 草稿 + Agent 集成）
- **方案**：调 `wenyan` CLI 做 Markdown→富文本→草稿箱
