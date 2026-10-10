# AGENT.md — 开发者指南

面向 AI 编码助手和人类开发者的项目结构说明。反映 post-fix (0.4.0-fix) 结构。

## 1. 目录结构

```
content-harbor/
├── backed/
│   ├── app/
│   │   ├── factory.py          # FastAPI 应用工厂 (create_app)
│   │   ├── routes/
│   │   │   └── (router 挂载)
│   │   └── middleware/
│   │       └── auth.py
│   ├── api/
│   │   ├── hub.py              # 所有 REST 端点的唯一入口
│   │   └── v1/
│   │       └── (hub → TaskManager 调度)
│   ├── core/
│   │   ├── permissions.py      # 权限校验
│   │   ├── human_click.py      # 人机协作点击模拟
│   │   └── security.py         # 安全辅助 (token、签名)
│   ├── service/publishing/
│   │   ├── hub.py              # Hub 编排器，聚合所有子系统
│   │   ├── db.py               # 数据库唯一真理源
│   │   ├── browser.py          # Patchright Chromium 适配
│   │   ├── gate.py             # AIGC 合规门禁
│   │   ├── ai.py               # OpenAI 兼容 LLM 调用
│   │   ├── tasks.py            # TaskManager
│   │   ├── humanize.py         # 人机模拟 (WPM/延迟)
│   │   ├── observability.py    # 日志/指标/可观测
│   │   └── adapters/
│   │       ├── __init__.py     # @register 注册器
│   │       ├── base.py         # PlatformAdapter 基类
│   │       ├── zhihu.py        # 知乎
│   │       ├── xiaohongshu.py  # 小红书
│   │       ├── wechat.py       # 微信公众号
│   │       ├── toutiao.py      # 头条号
│   │       ├── juejin.py       # 掘金
│   │       ├── csdn.py         # CSDN
│   │       ├── zhihu.py        # 知乎
│   │       ├── cnblogs.py      # 博客园 (XML-RPC)
│   │       ├── metaweblog.py   # 博客园元数据 (供 metaweblog 客户端用)
│   │       ├── oschina.py      # 开源中国
│   │       ├── segmentfault.py # SegmentFault
│   │       ├── toutiao.py      # 头条号
│   │       ├── bilibili.py     # B站专栏
│   │       └── wuyi_cto.py     # 51CTO
│   ├── config_unified.py       # 统一配置
│   └── cli.py                  # 命令行入口
├── web/src/                    # Vue3 + Element Plus 前端
├── scripts/
│   ├── check_all.{sh,ps1}      # 一键回归门禁（compileall/ruff/pytest/vite）
│   └── backup_data.py          # 数据备份（在线一致性快照）
├── docs/
│   ├── architecture/ARCHITECTURE.md   # 架构与 ADR
│   ├── audit/AUDIT.md                 # 存量审计快照（2026-09-22 时点）
│   ├── design/                        # M5 设计文档与技术债台账
│   ├── writing-style.md               # AI 写作风格档案
│   └── PLATFORM_PUBLISH_GUIDE.md      # 平台发布接入指南
├── deploy/                     # Docker 部署脚本
└── pyproject.toml
```

适配器注册是**导入副作用**：`adapters/__init__.py` 集中导入全部适配器模块，
`@register` 装饰器在导入时把类登记进 `base.ADAPTERS`。新增平台只需在该
`__init__.py` 加一行导入，不要依赖 `service.py` 的导入顺序。

## 2. 数据流

```
HTTP Request
    │
    ├─ 认证中间件 (HARBOR_API_TOKEN 校验)
    │
    ▼
api/hub.py
    │  ├─ 鉴权
    │  ├─ 请求体验证
    │  └─ 调用 get_task_manager()
    │
    ▼
TaskManager.submit(kind, payload)
    │  ├─ INSERT INTO tasks (...) VALUES (...)
    │  ├─ 返回 task_id
    │  └─ 触发 Worker
    │
    ▼
TaskManager Worker Thread (串行)
    │  ├─ UPDATE tasks SET status='running'
    │  ├─ 调用 Hub.<method>(payload)
    │  │   ├─ Gate.check(content)        ← AIGC 合规
    │  │   ├─ AI.write/rewrite/polish    ← 可选 LLM 步骤
    │  │   ├─ Adapter.publish(...)       ← 平台适配器
    │  │   └─ Browser.*                  ← Patchright 操控
    │  ├─ 结果 → 新增 publications 记录
    │  └─ Triage分流
    │       ├─ HUMAN_HINTS match → waiting_human
    │       ├─ RETRY_HINTS match  → retry (exponential backoff)
    │       └─ 其他                → fail / success
    │
    ▼
DB (db.py, SQLite)
```

**REST 异步模型**：`submit()` 立即返回 `task_id`，客户端轮询 `GET /api/hub/tasks/{id}` 获取进度。

**MCP 同步模型**：MCP Hub 直接调用 `hub.publish(...)` 等函数，绕过 TaskManager，同步返回结果。

## 3. 数据库 (db.py — 唯一真理源)

### 表结构

```sql
-- 账户信息
accounts (
  id TEXT PRIMARY KEY,
  platform TEXT NOT NULL,
  username TEXT,
  auth_json TEXT,          -- 序列化的登录凭证
  created_at TEXT,
  updated_at TEXT
)

-- 原始文章内容
articles (
  id TEXT PRIMARY KEY,
  title TEXT,
  content TEXT,
  content_type TEXT,       -- markdown / html
  created_at TEXT
)

-- 已发布记录（关联 accounts + articles）
publications (
  id TEXT PRIMARY KEY,
  account_id TEXT REFERENCES accounts(id),
  article_id TEXT REFERENCES articles(id),
  platform_post_id TEXT,   -- 平台侧 ID
  url TEXT,
  published_at TEXT,
  updated_at TEXT
)

-- 后台任务
tasks (
  id TEXT PRIMARY KEY,     -- UUID hex[:10]
  kind TEXT NOT NULL,      -- publish | update | sync | refresh | login | assist
  status TEXT NOT NULL,    -- pending | running | waiting_human | success | fail
  payload TEXT,            -- JSON
  result TEXT,             -- JSON
  error TEXT,
  attempts INTEGER DEFAULT 0,
  max_attempts INTEGER DEFAULT 3,
  created_at TEXT,
  updated_at TEXT
)

-- 元数据（迁移版本控制）
meta (
  key TEXT PRIMARY KEY,
  value TEXT
)
```

### 连接管理

- **LockedConnection**：线程安全包装，内部使用 `threading.RLock`
- 所有数据库操作通过 LockedConnection 序列化访问
- SQLite WAL 模式已启用

### 迁移机制

```python
# db.py
MIGRATIONS = [
    "CREATE TABLE IF NOT EXISTS ...",
    # 后续增量迁移...
]

SCHEMA_VERSION = 1  # meta.schema_version 存储当前版本
```

服务启动时 `init_db()` 按需执行迁移脚本。

## 4. TaskManager 约定

### API 签名

```python
task_id = task_manager.submit(kind: str, payload: dict) -> str
# kind: "publish" | "update" | "sync" | "refresh" | "login" | "assist"
# Returns: UUID hex[:10]

task_manager.resume(task_id: str, approved: bool) -> dict
# approved=True: 人工确认，继续最终发布
# approved=False: 人工拒绝，任务置 fail

status = task_manager.get_status(task_id: str) -> dict
```

### 任务生命周期

```
[submit] → pending → running ─┬─→ success
                               ├─→ fail (永久)
                               ├─→ waiting_human → [resume] → success / fail
                               └─→ pending (重试, attempts < MAX_ATTEMPTS)
```

### 分流逻辑 (Triage)

```python
# tasks.py
HUMAN_HINTS = ["验证码", "captcha", "登录", "二次验证", "人工"]
RETRY_HINTS = ["timeout", "network", "econnreset", "503"]

# 错误消息匹配流程
if any(h in error for h in HUMAN_HINTS):
    status = "waiting_human"
elif any(h in error for h in RETRY_HINTS) and attempts < MAX_ATTEMPTS:
    status = "pending"  # 重新排队
    # exponential backoff: sleep(2 ** attempts)
else:
    status = "fail"
```

| 常量 | 值 |
|------|-----|
| `MAX_ATTEMPTS` | 3 |
| 退避策略 | 指数退避 1s, 2s, 4s |

### Worker 约束

- **单线程串行**：一个 Worker 实例，一次只处理一个任务
- 启动时机：`factory.py` lifespan 中初始化并启动
- 关闭：`atexit` 或 lifespan shutdown 终止

## 5. 适配器约定

### 基类

```python
# adapters/base.py
class PlatformAdapter(ABC):
    id: str                    # "zhihu"
    name: str                  # "知乎"
    auth_method: str           # "browser" | "api" | "xml-rpc"
    needs_browser: bool        # True / False

    @abstractmethod
    def publish(self, page: Page, article: Article, draft_only: bool = False) -> dict:
        ...

    def update(self, page: Page, publication: Publication, article: Article) -> dict:
        raise NotImplementedError   # 可选
```

| 字段 | 说明 |
|------|------|
| `id` | 唯一标识符，小写英文 |
| `name` | 中文名 |
| `auth_method` | 认证方式 |
| `needs_browser` | 是否需要浏览器实例 |

### 注册方式

```python
# 在 adapters/__init__.py 中
_registry: dict[str, Type[PlatformAdapter]] = {}

def register(cls: Type[PlatformAdapter]):
    _registry[cls.id] = cls
    return cls

# 在每个适配器文件末尾
@register
class ZhihuAdapter(PlatformAdapter):
    id = "zhihu"
    ...
```

### 当前列表 (10 个)

> 本表由 `tests/test_docs_links.py::test_agent_md_adapter_tree_matches_reality`
> 与代码对照校验——改适配器而不同步本表，测试会红。

| 适配器 | 文件 | needs_browser |
|--------|------|---------------|
| 51cto | wuyi_cto.py | False |
| bilibili | bilibili.py | True |
| cnblogs | cnblogs.py | False |
| csdn | csdn.py | True |
| juejin | juejin.py | True |
| metaweblog | metaweblog.py | False |
| oschina | oschina.py | True |
| segmentfault | segmentfault.py | True |
| toutiao | toutiao.py | True |
| zhihu | zhihu.py | True |

### 新增适配器 Checklist

1. 在 `adapters/` 下创建 `{platform}.py`
2. 继承 `PlatformAdapter` 实现 publish()
3. 末尾 `@register` 装饰器
4. 在 `config_unified.py` 中添加平台默认配置
5. 更新 `docs/architecture/ARCHITECTURE.md` 平台适配器表

## 6. 开发命令

### 启动服务

```bash
cd backed
python -m uvicorn app.factory:create_app --host 0.0.0.0 --port 8000 --reload
```

### CLI 操作

```bash
python -m backed.cli <command>
python -m backed.cli sync                # 同步平台状态
python -m backed.cli refresh-login       # 刷新登录态
python -m backed.cli list-tasks          # 查看待处理任务
python -m backed.cli approve-task <id>   # 批准等待中任务
```

### 配置

- 开发环境：`config_unified.py` 默认值即可
- 生产环境：设置环境变量
  ```bash
  export HARBOR_SECRET_KEY="your-256-bit-secret"
  export HARBOR_DATABASE_URL="sqlite:///data/content_harbor.db"
  export HARBOR_API_TOKEN="your-api-token"
  ```

### 测试

测试套件已就位（278 个用例，`backed/tests/`），提交前跑一键门禁：

```bash
# Windows
pwsh -File scripts\check_all.ps1
# Linux / macOS / Git Bash
bash scripts/check_all.sh
```

门禁四道：`compileall` 语法 → `ruff` 静态 → `pytest` 单测 → `vite build` 前端。
单跑某一类：

```bash
cd backed
uv run pytest -q                                    # 全部
uv run pytest tests/test_tasks.py -q                # 任务引擎
uv run pytest tests/test_api_integration.py -q      # REST 接线
uv run ruff check .                                 # 静态门禁
```

`conftest.py` 会把 DB 路径、事件日志、webhook 派发线程全部关进 pytest 临时目录，
**不会碰开发库** `backed/service/data/hub.db`。

### 备份

```bash
cd backed
uv run python ../scripts/backup_data.py              # 到 ~/harbor-backups
uv run python ../scripts/backup_data.py --dry-run    # 只看计划
```

走 `sqlite3.Connection.backup()` 做在线一致性快照，不用停服务。`auth.json` 与
`config.json` 含凭据，脚本会拒绝把备份写到仓库内。

注意：测试不得启动真实 Hub（会拉起浏览器池 + 调度器 + atexit 钩子）——
需要 Hub 的地方用 `StubHub`（见 `tests/test_api_integration.py`）替换。

## 7. 提交规范

- 信息英文，body 中文
- Conventional Commits：`feat:` / `fix:` / `chore:` / `refactor:` / `docs:`
- 与架构/数据模型相关改动需更新此文件与 `docs/architecture/ARCHITECTURE.md`

## 8. 不要做的事

- 不要在 `db.py` 之外写原生 SQL
- 不要在适配器之外直接操作 Playwright context（必须通过 `browser.py`）
- 不要在 `hub.py` 之外创建 FastAPI router
- 不要绕过 TaskManager 持久化任务（除非 MCP 同步调用场景）
- 不要复用 scaffold 模式（v1/schemas/repository/_service.py 等已废弃模式）
