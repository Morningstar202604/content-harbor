# frontend-redesign.md — 前端重构设计（2026-10-14）

> 背景：用户反馈「前端不符合发文章逻辑、不像工作流」；且后端此时补齐了
> **真实发布通道**（human_confirmed / AI_DIRECT_PUBLISH）与 **AI 配置端点**（/ai/config）。
> 本文件是重构的唯一真理源（IA / 组件 / API 映射 / 替换清单）。

## 1. 设计立场

发布是主线，写作是主线的第一步。整个信息架构围绕一条流程：

```
写（AI 辅助） → 核（AIGC 门禁） → 发（真实上线） → 跟（任务/记录） → 配（AI/账号/定时/通知）
```

三条原则：
1. **真实发布是一等公民**：发布方式默认「立即发布（真实上线）」；「仅存草稿」是次选而非默认心智。
2. **状态永远可见**：平台登录态、门禁状态、任务进度（SSE）、每平台发布结果，全部贴在操作的旁边（右轨），不藏在二级弹窗。
3. **AI 是一等配置**：设置页第一 tab 即 AI（密钥/模型/路由/直发开关/二审模型/写作风格）。

## 2. 信息架构（导航）

| 导航 | 视角 | 解决的问题 |
|---|---|---|
| 写作台 | 单篇文章的全生命周期 | 写稿 / AI 工具 / 版本 / 质检 / **右轨发布** |
| 发布中心 | 所有文章的发布运营 | 待人工处置、待同步、发布记录、一键同步 |
| 任务中心 | 引擎心跳 | 全部任务 + 实时进度 + 恢复/放弃 |
| 设置 | 一次配好 | AI 模型 / 平台账号 / 定时发布 / Webhook 通知 |

## 3. 组件清单

**新写**
- `components/SideNav.vue` 侧栏导航（含 AI 就绪 / 待人工徽标）
- `views/WriteView.vue` 写作台三栏（列表 | 编辑器 | 发布轨）
- `views/PublishCenterView.vue` 发布中心
- `views/TasksView.vue` 任务中心
- `views/SettingsView.vue` 设置容器（tabs）
- `components/settings/AIPanel.vue` AI 密钥/模型/路由/门禁
- `components/settings/AccountsPanel.vue` 平台账号（登录/检测/登出/诊断/抓取）
- `components/settings/SchedulesPanel.vue` 定时发布
- `components/settings/WebhooksPanel.vue` Webhook + 站内通知
- `components/PublishRail.vue` 发布轨（取代弹窗 Wizard）

**保留（微调）**
- `components/ArticleEditor.vue`（编辑器；`publish` 事件改为聚焦发布轨）
- `components/ArticleList.vue` / `AIWriteDialog.vue` / `EmptyState.vue` / `BrandLogo.vue`
- `stores/*`（hub 编排 + 7 子 store 分层保留；settings store 新增）
- `styles/main.scss` 设计 token（晴空）全量保留，追加壳层/轨道样式

**删除（被取代）**
- `components/AppHeader.vue`（被 SideNav 取代）
- `components/ManagePanel.vue`（拆进发布中心/任务中心/设置）
- `components/PublishWizard.vue` + `composables/usePublishWizard.js`（被 PublishRail 取代）

## 4. 发布轨交互规格（PublishRail）

1. **选平台**：卡片网格，含登录态圆点（绿=在线/灰=未登录，点击未登录先弹「去登录」）；
   支持全选/清空；juejin/csdn 显示分类配置（本地记忆）。
2. **发布方式**（radio）：
   - 立即发布（真实上线）——默认；`draft_only=false`
   - 仅存草稿——`draft_only=true`（说明文案：先不公开，回头自己发）
3. **AI 稿合规条**（`source=ai` 且立即发布时出现）：
   - 已开 `AI_DIRECT_PUBLISH` → 蓝色提示「已开启 AI 直发（安全扫描+二审+AIGC 标识后直接上线）」
   - 未开 → 必须勾选「我已核验内容无误」才可发（`human_confirmed=true`）；附设置页指引
4. **发布按钮** → 任务引擎；右轨就地显示每平台进度（排队→执行中→成功链接/失败原因/待人工）
5. **已发状态区**：该文章每平台实例状态 + 打开链接 + 单平台更新 + 全量「同步所有平台」。

## 5. API 映射（前端 → 后端）

| 交互 | 端点 |
|---|---|
| 发布（真实/草稿/确认） | `POST /articles/{id}/publish` `{platforms, draft_only, human_confirmed, settings}` |
| 平台登录态/列表 | `GET /platforms`、`GET /accounts`、`GET /accounts/{pf}/check`、`POST .../login`、`DELETE .../{pf}`、`GET .../diagnose` |
| 任务与进度 | `GET /tasks`、`GET /tasks/{id}`、`POST /tasks/{id}/resume`、SSE `GET /events/stream` |
| 发布记录/待人工 | `GET /publications`、`GET /pending-human` |
| 更新/同步 | `POST /articles/{id}/update`、`POST /sync/pending` |
| AI 配置（新） | `GET/PUT /ai/config`、`POST /ai/config/test`、`GET /ai/gate`、`GET /ai/providers` |
| 定时 | `GET/POST/PUT /schedules`、`pause/resume/trigger/delete` |
| Webhook/通知 | `GET/POST/PUT/DELETE /webhooks`、`POST /webhooks/{id}/test`、`GET /notifications` |

## 6. 断点策略

- `>=1280`（sideDocked）：三栏常驻（列表 280 | 编辑器 flex | 发布轨 320）
- `>=1024`（listDocked）：列表常驻 + 编辑器；发布轨改右侧抽屉（点「发布」打开）
- `<768`（xs）：单栏；列表为抽屉；发布轨整屏抽屉
