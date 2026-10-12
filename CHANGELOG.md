# Changelog

---

## [0.7.0] - 2026-10-12

> 主题：**全仓审查 + 修复 0.7.0 拆分引入的运行时缺陷 + 补 AIGC 合规门禁缺口**。
> 测试用例 299 → 330。

### 新增：全仓代码审查与回归测试

审查员逐文件通读 `backed/` 全部 Python 源码（~14,800 行），产出
`review-findings.md`（29 条发现，含 A/B/C/D/E 五类定级）。本轮修复 14 条
关键缺陷，新增 `backed/tests/test_review_20261012.py`（31 用例）锁定所有修复。

### 修复（运行时缺陷）

- **F-29 `Hub._busy_for` 从未定义**：`service.py` 里 5 处 `with self._busy_for(...)`
  但 Hub 从未定义这个方法——只有 `BrowserPoolManager` 有。一运行到登录/检查/验证码
  路径就 `AttributeError`。这是 0.7.0 拆分引入的**必炸点**，现有 298 测试因走
  StubHub/DEMO 模式从未触发。已在 Hub 里补 `_busy_for` 委托。
- **F-05/F-06 `TaskManager._dispatch` 丢参数**：login 的 `timeout`/`on_captcha`、
  refresh 的 `limit` 全部被 API 层接收但 dispatch 硬编码丢弃，`LoginIn.timeout` 传了无效。
  现在从 `task.result` 读出来传给 hub 方法。
- **F-07 路径穿越**：`/accounts/{platform}/check`、`/accounts/{platform}/login` 等端点
  未校验 platform/account，攻击者传 `..` 或 `../../etc` 可以拼到 profile 路径上，
  触发 `shutil.rmtree` 删任意目录。所有账号端点加正则校验 `^[a-zA-Z0-9_-]{1,64}$`。
- **F-18/F-26 AIGC 门禁缺口**：`hub.update()` / `hub.sync_pending()` 完全不过
  `aigc_gate.apply_gate_before_publish`，AI 改写后直接同步上线绕过《AIGC 标识办法》。
  现在 update 也过安全扫描 + AI 源打 AIGC 标识。
- **F-13 占位符误报**：`gate._local_review` 把 `{{ }}` 当占位符，任何 Python f-string /
  Jinja / CSS 技术文档一跑就 reject。移出黑名单，占位符检测只在代码块外的正文做。
- **F-02 连接泄漏**：`_webhook_store.init(conn)` 自建 conn 后不 close，register/list_all
  每次调用泄漏一个 sqlite 连接。加 try/finally。
- **F-03 arity bug**：`ArticleStore.edit` 里 `get_pending_updates(conn, article_id)`
  实际只接受 1 个参数，一旦真被调用就 TypeError。删掉这行。
- **F-12 误发事件**：`_run_task` retry 分支也调 `on_task_complete`，把 retry 当完成发事件。
  只有 fail/human 终态才 emit。
- **F-24 吞中断**：`browser._bw_worker` 捕获 `BaseException`，把 `KeyboardInterrupt` /
  `SystemExit` 当普通异常吞掉。改成 `except Exception`。
- **F-25 死代码**：`BuiltinBrowser.start()` 用 `self.display is False` 判断，
  `ensure_display()` 从不返回 False，Linux 无 X 时不会降级到 headless。改成 `not self.display`。

### 清理

- **F-01 `check_all.ps1` 死锁 bug**：scriptblock 里的 `exit 1` 会终止整个 pwsh 进程
  而不是回到 try/catch，ruff 一红 4 步只跑 1 步，汇总行也打不出来。改成 `throw`。
- **F-10 死代码**：删除 `api/__init__.py::register_routers`（挂 `/api/hub` 但从未被调用，
  实际入口是 `api.hub.register_hub` 挂 `/api/v1/hub`）。
- **F-11 版本号**：`api/hub.py` 独立 app 的 version 从 0.2.0 更新到 0.7.0。
- **ruff F401**：清理 3 处未使用 import（`_webhook_store.time`、`urllib.request`、`crypto.base64`）。

### 新增测试

- **`test_review_20261012.py`（31 用例）** — 锁定本轮所有修复：
  平台名路径穿越防护（6 例）、dispatch 参数传递（2 例）、retry 不发完成事件（2 例）、
  AIGC 门禁 update 路径（2 例）、代码级断言（8 例）、占位符检测（4 例）。
- **`test_gate.py` 更新**：删除 `{{name}}` 占位符回归用例，新增模板语法不误报
  与代码块内 TODO 不误报的回归锁定。

### 门禁

`check_all.ps1` 四道全绿：compileall / ruff / pytest / vite build。


## [0.6.5] - 2026-10-10

> 主题：**给零覆盖的高风险区补测试，并修掉测试挖出的限流绕过漏洞**。
> 测试用例 176 → 278。

### 修复：限流可被一个请求头绕过

`middleware/rate_limiter.py` 的 `_get_client_ip` 无条件采信 `X-Forwarded-For`，
而该请求头由客户端自由填写。任何人每请求换一个 XFF 就拿到一个全新令牌桶，
**限流形同虚设**——而限流是安全边界上的关键一环，此前零测试覆盖。

改为只在**对端本身受信**（本机回环 / `TRUSTED_NETS` 网段）时才采信代理头。
受信判定直接复用 `api/hub.py` 既有约定（`_trusted_networks` / `_peer_is_trusted`），
不另造一套——本机代理部署仍能正确解析 XFF。

### 新增测试

- **`test_gate.py`（61 用例）** — AIGC 合规门禁，此前零直接覆盖。
  它是《人工智能生成合成内容标识办法》的落地实现（显式标识 + 人审闸门），
  错了不是功能 bug 而是合规事故。四道闸门全覆盖：安全扫描（含误阳性排查）、
  AIGC 标识（幂等 / ext 保全 / 损坏 JSON 兜底）、双模型审查（安全扫描优先于
  二审、LLM 失败降级留痕）、发布闸门（AI 源禁裸奔上线）。
- **`test_rate_limiter.py`（24 用例）** — 含限流绕过的回归锁定、跳过路径、
  令牌桶突发/补充/独立键/重置，以及 TRUSTED_NETS 配置容错。
- **`test_human_click.py`（17 用例）** — 贝塞尔采样（steps≤0 除零保护、
  端点精确、控制器外插不发散）、落点夹取（只约束落点，曲线中间点本就该在
  元素外）、候选选择器拼装与降级。

### 顺带纠正

`test_gate.py` 首轮写坏了一条断言（以为 `add_aigc_label` 在文章模型为空时会
回退成别的值）。读实现确认是测试写错而非代码 bug，已改为分别覆盖"参数空则回退
文章模型"与"两者皆空则保持空"两种真实语义。

---

## [0.6.4] - 2026-10-10

> 主题：**清掉全部存量技术债**（tech-debt 台账 #8 + #11），并纠正台账对 #3 的过期描述。
> 无业务行为变更。

### 门禁

- **ruff 门禁从 3 条规则扩到全量卫生规则**（`E4/E7/E9/F`，仅 `E402` 显式豁免）。
  之前 0.6.3 定的"全开只会产出 58 条噪音"在本轮被证伪——**清完之后门禁是绿的**，
  噪音是一次性存量而非持续增量。
- `E402` 的 9 处经逐一读上下文确认是**有意为之的后置 import**（`config/__init__.py`
  先定义 `__all__` 再 re-export；`service.py` 的跨模块 import 必须排在常量之后，
  `:37` 的"导入即注册"尤其不能动）。豁免理由写进 `pyproject.toml` 注释，不是"以后再说"。

### 清理（68 条 → 0）

- F401 死 import 29 处、F541 无占位符 f-string 8 处、E401 单行多导入 1 处：
  走 `ruff --fix` 后**逐文件读 diff 复核**。
- F841 死变量 6 处、F811 重定义 5 处：人工确认无行为风险后手改。
- E702 分号多语句 10 处：手工拆行，保持浏览器操作顺序逐字不变。
- 顺带清掉 `api/hub.py` 里 3 处裸 SQL 已在本轮之前下沉完毕（0.6.1）。

**过程中抓到并修掉一个真 bug**：`ruff --fix` 删掉了 `service.py` 中
`wait_human_captcha` 的唯一引入点——该符号只在 `solve_captcha` 的浏览器分支
用到，测试全绿也照样上线炸。由 F821 当场抓住，并新增
`test_no_undefined_names_anywhere` 把 F821 零命中纳入回归。

### 文档迁移（tech-debt #11）

- `ARCHITECTURE.md` → `docs/architecture/ARCHITECTURE.md`（git 记录为 rename，历史保留）
- `AUDIT.md` → `docs/audit/AUDIT.md`
- 新增 `test_docs_links.py`（16 用例）：相对链接可达性 + 迁移落点固定 +
  **AGENT.md 适配器清单与代码对照**——该清单此前写着"11 个"却列出 5 个不存在的
  文件（douyin/weibo/sf 等），且漏掉 6 个真实存在的，现按 `ADAPTERS` 实际内容重写。

### 台账纠正

- **#3（update/sync 切流引擎）标记为早已完成**：核实发现 `update_single`
  （`service.py:876`，注释写明"R3 门禁：行为逐字不变"）已抽出、`tasks._dispatch`
  已处理 update/sync、`api/hub.py:263-276` 三套入口已合一无 legacy 分支。
  台账写于 2026-09-22 基线，之后代码重构过而台账没跟上。该项从未是待办。
- **#5（共享驱动崩溃自愈）维持不还**：其触发条件是"首次真实崩溃或部署到无人值守
  环境"，均未发生。

版本 0.6.3 → 0.6.4（无运行时行为变更，`uv.lock` 依赖集合不变）。

---

## [0.6.3] - 2026-10-10

> 主题：**依赖管理收口 + Pydantic v2 API 收尾**。无行为变更。

### 移除

- **删 `web/package-lock.json`**：与 `web/pnpm-lock.yaml` 双 lockfile 并存会让本地
  与 CI 装出不同的依赖树。README / README.en / ci.yml / check_all 四处早已一律走
  pnpm，全仓库零 npm 调用，故删 npm 那份（tech-debt 台账 #10）。
  若 pnpm 装出问题，执行 `pnpm install` 会按 `pnpm-lock.yaml` 精确还原。

### 修复

- **`api/hub.py` 4 处 `.dict()` → `.model_dump()`**：`ArticleIn` / `ArticlePatch` /
  `SchedulePatch` / `WebhookIn` 四处调用。`.dict()` 在 Pydantic v2 已弃用、v3 移除，
  而 `pyproject.toml` 写的是 `pydantic>=2.0.0`（允许装 v3）——照现状升级即炸。

### 门禁

- `pyproject.toml` 新增 `filterwarnings`：把 `PydanticDeprecatedSince20` 升级为
  **error**。这类问题编译期查不出、运行时也不炸，只在升级依赖那天爆；
  现在让它在测试里红掉。护栏有效性已反向验证（注入一处 `.dict()` → 测试转红）。

版本 0.6.2 → 0.6.3（无运行时行为变更，故不动 `uv.lock` 依赖集合）。

---

## [0.6.2] - 2026-10-10

### 新增：数据备份（tech-debt 台账 #9）

`docs/design/m5-data.md:61` 当时把备份留给手工 `cp` 并注明"更稳的做法是
`sqlite3 .backup`，M6 可做成脚本"。现在做成脚本了：

- `scripts/backup_data.py`，在 `backed/` 下 `uv run python ../scripts/backup_data.py`
- **在线一致性快照**：走 `sqlite3.Connection.backup()` 而非 `cp`。SQLite 跑 WAL
  且服务常在写，`cp` 拿到的是半截事务副本——能打开但可能缺最近几条写入。
  **不需要停服务**。
- 备份完对副本跑 `PRAGMA integrity_check` 并只读打开校验，跑不通不算备份成功
  （否则"生成了个文件"会被误当成"备份好了"）。
- 备份清单按 `m5-data.md` §4 的敏感分级处置：`hub.db` 可直接备份；
  `profiles/*.auth.json`（session cookie）与两份 `config.json`（明文 API Key）
  属敏感项，落盘权限收紧。
- **拒绝备份到仓库内**：凭据类文件落进仓库就有被 commit 的风险，直接拒绝并
  给出仓库外路径建议，退出码 2。
- 资产缺失时"能备的都备、缺的如实报告"，只有一件都没有才算失败——
  hub.db 缺失往往是数据事故信号，那时更该把还在的凭据备下来而不是整体失败。
- `--keep N` 按天清理，但永远保留最新一份（清理策略不能把备份清空）。
- `--dry-run` / `--include-profiles` / `--json`。
- 16 个用例覆盖：仓库内拒绝、并发写时的一致性快照、副本可读性与完整性、
  敏感文件内容与权限、输出不泄露任何 secret 值、清理策略的边界。

同时把 tech-debt 台账的 T1/T2/#9 标注为已清偿（#1 无版本基线、#2 无一键门禁、
#9 无备份分别由 0.6.1 与本版完成）。

---

## [0.6.1] - 2026-10-10

> 主题：**修隐患 + 补测试门禁**。无新功能；发现并修掉 6 个"上过线但跑不通"的缺陷，
> 然后把 tech-debt 台账 T2 的"一键回归门禁"落地。

### 修复（全部由新增测试先复现，再改源码）

| # | 症状 | 根因 | 位置 |
|---|---|---|---|
| 1 | **后端完全起不来**，`create_app()` 直接 ImportError | `utils/audit.py` 留着 `from sqlalchemy.orm import Session`，而 SQLAlchemy 早就不在依赖里（死 import） | `backed/utils/audit.py` |
| 2 | **MCP Server 起不来**，`python mcp_server.py` 报无 `fastmcp` 模块 | 用 `from fastmcp import FastMCP`，但 `mcp>=1.0` 的导入路径是 `mcp.server.fastmcp`；且 `run(transport="sse", port=)` 不接 `port` 参数 | `mcp_server.py` |
| 3 | **Webhook 注册必 500**，POST `/webhooks` 永远失败 | `c.lastrowid` 写在 `Connection` 上——该属性在 `Cursor` 上 | `backed/service/publishing/events.py` |
| 4 | **定时发布静默失效**：到期任务每 30 秒炸一次且永远不执行 | `_execute` 把入参 `task_row` 写成 `row`（`_tick` 的循环变量名），F821；失败分支自己也引用 `row`，于是 `next_run` 永不更新。空表达式建出的任务 `next_run=NULL` 同样是僵尸 | `backed/service/publishing/scheduler.py` |
| 5 | **回滚不落痕**，历史里查不到 `change_kind='rollback'` 记录 | 回滚时快照的是 `dict(art)`（回滚前内容），与刚写入的 `pre-rollback` 内容哈希相同，被去重逻辑吞掉 | `backed/service/publishing/versions.py` |
| 6 | **`GET /platforms` 返回空数组**，平台列表像不存在 | 适配器"导入即注册"，但注册只发生在 `service.py` 被导入时；先打到 `/platforms` 的进程拿到的注册表是空的 | `backed/service/publishing/adapters/__init__.py`、`backed/api/hub.py`、`mcp_server.py` |

附带：`tags.merge_tags` 合并 `py,Python` → 留下 `Python,Python` 重复标签（去重只护了映射侧）。

### 测试与门禁（tech-debt T2）

- 新增 `backed/tests/`，**159 个用例**：
  - 模块导入层（每个真实模块裸 import，专抓"编译过但装不上"的依赖漏洞）
  - DB 层：schema / 迁移幂等 / `LockedConnection` 6 线程串行化 / 文章与发布 CRUD / 跨表查询
  - 任务引擎：提交、串行消费、验证码→人工、网络错误→重试 3 次→失败、人工恢复、串行性
  - 标签治理：归一化、别名合并、合并去重、智能降级
  - 版本历史：快照去重、回滚、回滚的回滚、行级 diff、裁剪
  - 事件系统：webhook CRUD、HMAC 签名、通知环形缓冲、任务事件映射
  - 调度器：表达式解析 / CRUD / 投递失败推迟 / tick 拾取
  - REST 接线：文章 CRUD、任务生命周期、webhooks、tags、pending-human、platforms 走真实 FastAPI TestClient
- `conftest.py` 把 DB / 事件日志 / webhook 派发线程全关进 pytest 临时目录，测试不碰开发库
- 新增 `scripts/check_all.ps1` 与 `scripts/check_all.sh`：compileall → ruff → pytest → vite build，
  任一步失败即停，末行给 PASS/FAIL
- `pyproject.toml` 新增 `[tool.ruff]`：门禁只查 `E9/F7/F82`（未定义名、运行时错误、语法错误），
  风格与卫生类存量债暂不纳入，避免 58 条噪音把门禁变成没人看的东西
- CI 升级：backend job 增加 ruff + pytest；新增 frontend job 跑 `pnpm build`
- `.gitignore` 补 `backed/service/data/` 与 `*.db-wal` / `*.db-shm`（WAL 边车文件）
- `api/hub.py` 清掉 3 处裸 SQL，下沉到 `db.py` 新增的 `list_pending_human` /
  `list_publications_joined` / `list_failed_jobs`（遵守 AGENT.md §8）
- `uv.lock` 重新解析：此前 lock 与 `pyproject.toml` 已不同步（lock 里还留着
  aiomysql/pymysql/sqlalchemy/greenlet），`uv sync` 一次就掉进"缺依赖起不来"

---

## [0.6.0] - 2026-10-09

### 新增：多模型管理

- **8 个 AI Provider 预置**：DeepSeek / OpenAI / Anthropic / Kimi / 通义千问 / 智谱 / Ollama 本地
- **任务分级路由**：写作用 premium，润色用 standard，标签/摘要/大纲/SEO 用 economy
- **自动故障转移**：某个 Provider 连续失败 3 次冷却 2 分钟，自动切到下一可用
- **按请求指定模型**：任意 AI 调用传 `model="provider:model_name"` 绕过路由
- **前端模型下拉**：AI 写稿弹窗新增 Provider · 模型选择，留空走自动路由
- **CLI `--model` / `--provider`**：命令行指定模型和 Provider
- REST: `GET /ai/providers` · `GET /ai/status` (enriched)

### 新增：事件 / 通知系统

- **Webhook 注册**：URL + 事件过滤 + HMAC 签名，事件异步 POST 推送
- **事件类型**：task.ok / task.failed / task.waiting_human / publish.ok / publish.failed 等 10 种
- **站内通知**：环形缓冲最近 200 条，`GET /notifications` 拉取
- **自动禁用僵尸 Webhook**：连续失败 5 次暂停
- **任务完成自动触发事件**：TaskManager 内建 emit 节点
- REST: `GET/POST/PUT/DELETE /webhooks/{id}` · `POST /webhooks/{id}/test` · `GET /notifications`

### 新增：内容质检

- **可读性评分**：基于句长、段落长度、标题密度、代码占比；0-100 + 等级
- **SEO 评分**：TDK 完整度、关键词分布、H 标签结构、图片 alt、内链数
- **近似重复检测**：MinHash + Jaccard 查重，阈值 35%
- **一键运行**：`content_qa()` 返回总分 + 分项 + 改进建议
- 前端编辑器「视图与 AI」下拉新增「内容质检」条目 + 圆形总分图
- REST: `POST /articles/{id}/qa` · `POST /qa/analyze`

### 新增：MCP Server（FastMCP）

- **16 个 MCP Tool**：覆盖文章 / AI 写稿 / 发布 / 任务 / 质检 / 标签 / Provider
- **stdio + SSE** 两种传输，对接 Claude Code / Cursor / Windsurf
- 文件：`mcp_server.py`（项目根目录，独立运行）

### 前端改善

- AI 写稿弹窗增加模型选择器（按 Provider 分组，标注经济/均衡/旗舰）
- 文章编辑器新增「内容质检」菜单项 + 质检报告弹窗（圆形总分 + 可读性/SEO/重复度 + 改时建议）
- Element Plus 改为全局注册（uniplugin 轻量化），包体略大但构建更稳定

---

## [0.5.0] - 2026-10-09

### 新增：AI 工作流完整工具链

- **AI 翻译**：`ai_translate` — Markdown 文章翻译（保留代码块不动）到 en/ja/ko/fr/de
- **配图提示生成**：`ai_image_prompts` — 从正文提炼 3 个英文文生图 prompt（兼容 SDXL/Flux/DALL·E）
- **大纲提炼**：`ai_outline` — 从 Markdown 内容提取标题层级树
- **SEO 元数据**：`ai_seo` — 自动生成 seo_title / seo_description / slug / keywords
- **文章克隆**：`clone` — 复制已有文章为新草稿
- **写作模板**：4 个预置模板（教程/观点/深度剖析/资讯简评）

### 新增：定时发布调度器

- 守护线程每 30 秒轮询 `scheduled_tasks` 表，投递到 TaskManager
- 支持 once / daily / weekly / cron 四种调度类型
- CLI: `schedule-add` / `schedule-list` / `schedule-del` / `schedule-trigger`

### 新增：文章版本管理

- 改文章前自动快照到 `version_history` 表（sha256 去重）
- 回滚 / 行级 diff / AI 改写润色前自动存版本
- CLI: `versions` / `rollback`

### 新增：标签治理

- `tag_stats` 表 + `alias_map` 同义合并
- 合并 / 重命名 / 别名三步治理 + 词云展示
- CLI: `tags` / `tag-sync` / `tag-rename`

### 前端

- 编辑器「视图与 AI」下拉扩展（翻译/配图/大纲/SEO/克隆/版本历史）
- 新 `VersionDrawer` + `AIToolDialog` 组件
- ManagePanel 新增「定时任务」+「标签治理」标签页

### 文档

- ARCHITECTURE.md 新增 D6-D9 + API 路径总览
- CHANGELOG.md 本条目

---

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.4.1] - 2026-10-09

### 文档打磨

- **README.md 全面重写**：修复所有过时引用（`deplay` → `deploy`、`/api/v1` CRUD 路由、MCP 入口、`markdown-it` → `md-editor-v3`、`server/static` 构建路径）；删除 E2E 测试引用（测试套件已拆除）；更新仓库地址为多镜像表格
- **README.en.md 全面重写**：与中文版内容同步，专注国际开发者视角
- **ARCHITECTURE.md 全面重写**：修复目录结构（不再列举 `xiaohongshu` / `wechat` 等不存在的适配器）、修复 API 路径（删除 `/api/v1/*` 引用）、新增 ADR 设计决策一节（统一任务引擎、Patchright、单实例浏览器、双库合一、异步轮询）
- **CHANGELOG.md 同步更新**

### 浏览器启动修复

- `browser.py` `_find_chrome()` 新增 `/opt/playwright` 搜索根和 `chromium-*/chrome-linux64/chrome` 模式，解决沙箱环境内 Chromium 二进制找不到的问题

### 前端组件打磨

- 字体系统重构：`--font-serif` / `--font-disp` 语义化命名，真正区分展示体与代码块；中英字体栈优化（零外部请求）
- 删除 `App.vue` 中不再使用的 `.fab` 浮动按钮样式残留
- `vite.config.js` 修正 `manualChunks.md` 从 `markdown-it` → `md-editor-v3`；开发代理目标改为 `:8000`（当前默认端口）

## [0.4.0-fix] - 2026-10-09

### 重大清理

- **删除 scaffold 遗留**
  - 移除 `api/v1/` 孤立的 scaffold router
  - 移除 `models/` Pydantic 模型层（无实际依赖）
  - 移除 `schemas/` 校验层（无实际使用）
  - 移除 `repository/` 仓储抽象层（直连 db.py 即可）
  - 移除 `*_service.py` 重复服务层（article_service、account_service、job_service、publication_service、task_service）
  - 合计减少约 800 行无用代码

- **删除幽灵基础设施**
  - 移除 `core/cache.py`（从未被调用，仅定义类）
  - 移除 `core/queue.py`（从未被调用，基于 asyncio.Queue 的空实现）

- **移除 scaffold 遗产**
  - 移除 `events.py`（空事件钩子）
  - 移除 `router.py`（空路由器基础结构）
  - 移除 `config/settings.py`（已统一到 config_unified.py）

- **统一持久化层**
  - 保留 `db.py` 原生 SQLite SQL 作为唯一持久化层
  - 移除 SQLAlchemy ORM 依赖（不再需要 ORM 抽象）
  - 所有表结构定义集中在 `db.py` + `MIGRATIONS` 列表

- **测试清理**
  - 删除 `backed/tests/` 中引用 scaffold 的旧测试文件
  - 待后续补充针对性单元测试与集成测试

### 修复

- **humanize.py**
  - 修复 `human_type` 公式 bug：原公式导致打字速度被 WPS_EM 分母稀释
  - 修复后有效 WPM 从 48-84 提升到配置的 240-420 范围
  - 移除冗余的类封装，改为纯函数

- **observability.py**
  - 删除死代码 `_observe_with_max`（废弃的观察模式）
  - 删除 `M_*` 常量组（从未引用）
  - 删除 monkey-patch 逻辑（破坏函数签名，干扰调试）

- **config_unified.py**
  - `ProductionConfig.secret_key` 改为从 `HARBOR_SECRET_KEY` 环境变量读取
  - `ProductionConfig.database_url` 改为从 `HARBOR_DATABASE_URL` 环境变量读取
  - 缺失时抛出 `ValueError` 而非静默回退到默认值

- **api/hub.py**
  - 移除模块加载时的全局 Hub 副作用
  - 改为惰性单例工厂模式 `get_hub()`
  - 移除导入时的 `from service.publishing.hub import Hub` 全局实例化

- **app/factory.py**
  - `lifespan` 简化为 DB 初始化 + logging 配置
  - 移除 cache/queue 初始化（随幽灵基础设施删除）
  - 移除 scaffold router 注册

- **安全**
  - `api_token` 未配置时自动生成 UUID4
  - 启动时打印警告日志：`Generated api_token=*** — set HARBOR_API_TOKEN in production`
  - 生产模式必须显式指定 token

### 前端修复

- 删除 `App.vue` 中未使用的 `onRefresh` / `refreshing` 状态管理
- 删除 `ArticleList.vue` 中与 ArticleStore 重复的过滤逻辑（单一数据源原则）
- `ArticleEditor.vue` 补全 `is-active-cmd` 样式类（编辑态视觉反馈）

### 重命名

- `deplay/` → `deploy/` （`git mv`，修正拼写错误）

### 依赖更新

- `pyproject.toml`
  - 移除 `sqlalchemy`（不再需要 ORM）
  - 移除 `aiosqlite`（不再需要异步 SQLite）
  - 移除 `aiomysql`（不再需要 MySQL 异步驱动）
  - 移除 `greenlet`（SQLAlchemy 附带依赖）
  - 版本号对齐 `0.4.0-fix`

---

_Template for future entries:_

## [Unreleased]

### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security
