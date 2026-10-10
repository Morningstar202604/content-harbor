# -*- coding: utf-8 -*-
"""MCP 的 Wechatsync 外部执行器适配层回归。

设计前提（决定了这些用例在断言什么）：Wechatsync 是**可选后端**，不是替代品。
它跑在用户本机的 Chrome 扩展里、服务端通常没装。所以契约的核心不是"能调通
外部进程"，而是——

    外部执行器任何形态的不可用，都必须变成结构化返回，
    绝不能让异常冒泡打断 MCP 会话，也绝不能影响原有 20 个 tool。

这条如果破了，内容港会从"多一个可选能力"退化成"整个 MCP 不可用"。
"""

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import mcp_server as ms  # noqa: E402


@pytest.fixture(scope="module")
def tools():
    return asyncio.run(ms.mcp.list_tools())


@pytest.fixture
def fake_hub(monkeypatch):
    """替换 Hub 单例：本模块只关心转发逻辑，不该真连数据库。"""
    class _Fake:
        def get(self, aid):
            if aid == 1:
                return {"id": 1, "title": "文章一", "content_md": "# 标题\n\n正文"}
            return None

    h = _Fake()
    monkeypatch.setattr(ms, "_get_hub", lambda: h)
    return h


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("WECHATSYNC_TOKEN", raising=False)


# ---------------- Tool 注册契约 ----------------

def test_three_wechatsync_tools_registered(tools):
    names = {t.name for t in tools}
    assert {"wechatsync_status", "wechatsync_publish",
            "wechatsync_platforms"} <= names


def test_existing_tools_not_broken(tools):
    """原有 20 个 tool 必须一个不少——转发层是加法不是替换。"""
    names = {t.name for t in tools}
    legacy = {
        "list_articles", "get_article", "create_article", "update_article",
        "ai_write_article", "ai_rewrite_article", "ai_polish_article",
        "ai_translate_article", "ai_image_prompts", "publish_article",
        "update_remote_article", "list_platforms", "list_providers",
        "get_task", "resume_task", "quality_check", "analyze_text",
        "list_tags", "suggest_tags", "import_markdown",
    }
    missing = legacy - names
    assert not missing, f"原有 tool 丢失：{missing}"
    assert len(names) >= 23


def test_every_tool_has_description(tools):
    """docstring 就是给 Agent 看的说明，缺了就等于该 tool 不存在。"""
    for t in tools:
        assert (t.description or "").strip(), f"{t.name} 缺描述"


def test_publish_tool_schema_has_expected_params(tools):
    t = [x for x in tools if x.name == "wechatsync_publish"][0]
    props = set(t.inputSchema.get("properties", {}))
    assert {"article_id", "platforms", "title", "cover", "dry_run"} <= props


# ---------------- 就绪探测 ----------------

def test_status_reports_not_installed(monkeypatch):
    monkeypatch.setattr(ms, "_ws_bin", lambda: "")
    st = ms.wechatsync_status()
    assert st["ok"] is True
    assert st["installed"] is False
    assert st["ready"] is False
    assert "@wechatsync/cli" in st["note"]
    assert "WECHATSYNC_TOKEN" in st["note"]


def test_status_reports_missing_token(monkeypatch):
    monkeypatch.setattr(ms, "_ws_bin", lambda: "/usr/bin/wechatsync")
    monkeypatch.delenv("WECHATSYNC_TOKEN", raising=False)
    st = ms.wechatsync_status()
    assert st["installed"] is True
    assert st["has_token"] is False
    assert st["ready"] is False


def test_status_reports_ready(monkeypatch):
    monkeypatch.setattr(ms, "_ws_bin", lambda: "/usr/bin/wechatsync")
    monkeypatch.setenv("WECHATSYNC_TOKEN", "t")
    st = ms.wechatsync_status()
    assert st["ready"] is True
    assert st["note"] == "就绪"


def test_status_always_advertises_fallback():
    """降级时必须告诉 Agent 还有内置适配器可用。"""
    st = ms.wechatsync_status()
    assert st["fallback"]
    assert "publish_article" in st["fallback"]


# ---------------- 不可用时的降级（核心契约）----------------

def test_publish_degrades_when_cli_missing(monkeypatch, fake_hub):
    monkeypatch.setattr(ms, "_ws_bin", lambda: "")
    r = ms.wechatsync_publish(1, "juejin")
    assert r["ok"] is False
    assert r["available"] is False
    assert "npm install" in r["hint"]


def test_platforms_degrades_when_cli_missing(monkeypatch):
    monkeypatch.setattr(ms, "_ws_bin", lambda: "")
    r = ms.wechatsync_platforms()
    assert r["ok"] is False
    assert r["available"] is False


def test_publish_degrades_on_timeout(monkeypatch, fake_hub):
    """扩展没开会一直等到超时——必须转成结构化失败，不能挂住 MCP。"""
    monkeypatch.setattr(ms, "_ws_bin", lambda: "/usr/bin/wechatsync")

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="wechatsync", timeout=30)

    monkeypatch.setattr(ms.subprocess, "run", boom)
    r = ms.wechatsync_publish(1, "juejin")
    assert r["ok"] is False
    assert r["available"] is True          # 装了，只是连不上
    assert "超时" in r["error"]
    assert "Chrome" in r["hint"]


def test_publish_degrades_on_oserror(monkeypatch, fake_hub):
    monkeypatch.setattr(ms, "_ws_bin", lambda: "/usr/bin/wechatsync")

    def boom(*a, **k):
        raise FileNotFoundError("wechatsync")

    monkeypatch.setattr(ms.subprocess, "run", boom)
    r = ms.wechatsync_publish(1, "juejin")
    assert r["ok"] is False
    assert r["available"] is True
    assert "FileNotFoundError" in r["error"]


def test_publish_surfaces_cli_stderr(monkeypatch, fake_hub):
    monkeypatch.setattr(ms, "_ws_bin", lambda: "/usr/bin/wechatsync")

    class P:
        returncode = 1
        stdout = ""
        stderr = "需要安装 Chrome 扩展"

    monkeypatch.setattr(ms.subprocess, "run", lambda *a, **k: P())
    r = ms.wechatsync_publish(1, "juejin")
    assert r["ok"] is False
    assert "Chrome 扩展" in r["error"]
    assert r["returncode"] == 1


# ---------------- 参数与内容处理 ----------------

def test_publish_rejects_missing_article(fake_hub):
    with pytest.raises(ValueError, match="不存在"):
        ms.wechatsync_publish(999, "juejin")


def test_publish_rejects_empty_platforms(fake_hub):
    with pytest.raises(ValueError, match="platforms"):
        ms.wechatsync_publish(1, "   ")


def test_publish_builds_expected_command(monkeypatch, fake_hub):
    monkeypatch.setattr(ms, "_ws_bin", lambda: "/usr/bin/wechatsync")
    seen = {}

    class P:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def capture(argv, **k):
        # subprocess.run([bin, *args], ...) —— argv 是单个列表参数
        seen["args"] = list(argv[1:])
        return P()

    monkeypatch.setattr(ms.subprocess, "run", capture)
    ms.wechatsync_publish(1, "juejin,csdn", title="改标题", dry_run=True)
    a = seen["args"]
    assert a[0] == "sync"
    assert "-p" in a and "juejin,csdn" in a
    assert "-t" in a and "改标题" in a
    assert "--dry-run" in a


def test_publish_omits_dry_run_when_false(monkeypatch, fake_hub):
    """dry_run=False 才是真发布，标志必须真的去掉。"""
    monkeypatch.setattr(ms, "_ws_bin", lambda: "/usr/bin/wechatsync")
    seen = {}

    class P:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(ms.subprocess, "run",
                        lambda argv, **k: (seen.update(args=list(argv[1:])), P())[1])
    ms.wechatsync_publish(1, "juejin", dry_run=False)
    assert "--dry-run" not in seen["args"]


def test_publish_writes_article_content_to_temp(monkeypatch, fake_hub):
    monkeypatch.setattr(ms, "_ws_bin", lambda: "/usr/bin/wechatsync")
    written = {}

    class P:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def capture(argv, **k):
        # subprocess.run([bin, *args], ...) —— argv 是单个列表参数
        tmp = Path(argv[2])
        written["text"] = tmp.read_text(encoding="utf-8")
        written["path"] = tmp
        return P()

    monkeypatch.setattr(ms.subprocess, "run", capture)
    ms.wechatsync_publish(1, "juejin")
    assert "正文" in written["text"]


def test_publish_cleans_up_temp_file(monkeypatch, fake_hub):
    """文章内容不得留在磁盘上——临时文件必须删掉。"""
    monkeypatch.setattr(ms, "_ws_bin", lambda: "/usr/bin/wechatsync")
    seen = {}

    class P:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def capture(args, **k):
        seen["path"] = Path(args[1])
        return P()

    monkeypatch.setattr(ms.subprocess, "run", capture)
    ms.wechatsync_publish(1, "juejin")
    assert not seen["path"].exists()


def test_publish_cleans_up_temp_file_even_on_failure(monkeypatch, fake_hub):
    monkeypatch.setattr(ms, "_ws_bin", lambda: "/usr/bin/wechatsync")
    seen = {}

    def boom(argv, **k):
        seen["path"] = Path(argv[2])
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(ms.subprocess, "run", boom)
    ms.wechatsync_publish(1, "juejin")
    assert not seen["path"].exists()


def test_publish_echoes_context(monkeypatch, fake_hub):
    monkeypatch.setattr(ms, "_ws_bin", lambda: "")
    r = ms.wechatsync_publish(1, "juejin")
    assert r["article_id"] == 1
    assert r["platforms"] == "juejin"
    assert r["dry_run"] is True