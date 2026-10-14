# -*- coding: utf-8 -*-
"""回归测试：锁定 2026-10-14 审查收尾轮修复。

覆盖：
- F-09 密钥文件权限：Windows 走 icacls 去继承+只授当前用户；失败只降级告警不炸
- F-14 站内通知缓冲：测试间必须清空（conftest autouse 夹具），跨测试不串
- F-27 版本回滚：目标版本与当前内容相同 → 显式"无需回滚"，不写历史行
"""

import subprocess

import pytest

from service.publishing import crypto
from service.publishing import db
from service.publishing import versions
from service.publishing import _event_notifier as notifier


class _FakeResult:
    returncode = 0
    stderr = b""


# ---------------------------------------------------------------------------
# F-09 密钥文件权限收紧
# ---------------------------------------------------------------------------

def test_restrict_key_file_windows_invokes_icacls(tmp_path, monkeypatch):
    """Windows 下必须调 icacls：去继承（/inheritance:r）+ 只授权当前用户。"""
    key = tmp_path / ".fernet_key"
    key.write_bytes(b"k")
    monkeypatch.setattr(crypto.os, "name", "nt")
    monkeypatch.setenv("USERNAME", "tester")
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        return _FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)
    crypto._restrict_key_file(key)
    assert calls, "Windows 下应调用 icacls"
    argv = calls[0]
    assert argv[0] == "icacls"
    assert "/inheritance:r" in argv
    assert "/grant:r" in argv
    assert "tester:F" in argv
    assert str(key) in argv


def test_restrict_key_file_tolerates_missing_icacls(tmp_path, monkeypatch):
    """icacls 不存在也不许炸——密钥已生成，权限收紧失败只降级告警。"""
    key = tmp_path / ".fernet_key"
    key.write_bytes(b"k")
    monkeypatch.setattr(crypto.os, "name", "nt")
    monkeypatch.setenv("USERNAME", "tester")

    def boom(*a, **kw):
        raise FileNotFoundError("icacls")

    monkeypatch.setattr(subprocess, "run", boom)
    crypto._restrict_key_file(key)  # 不抛异常即通过


def test_restrict_key_file_tolerates_icacls_timeout(tmp_path, monkeypatch):
    """icacls 卡死超时（网络盘等）也只降级告警——TimeoutExpired 不是 OSError 子类，必须显式兜住。"""
    key = tmp_path / ".fernet_key"
    key.write_bytes(b"k")
    monkeypatch.setattr(crypto.os, "name", "nt")
    monkeypatch.setenv("USERNAME", "tester")

    def hang(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="icacls", timeout=10)

    monkeypatch.setattr(subprocess, "run", hang)
    crypto._restrict_key_file(key)  # 不抛异常即通过


def test_restrict_key_file_posix_skips_icacls(tmp_path, monkeypatch):
    """非 Windows 平台不应调用 icacls（POSIX 只走 chmod）。"""
    key = tmp_path / ".fernet_key"
    key.write_bytes(b"k")
    monkeypatch.setattr(crypto.os, "name", "posix")
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **kw: pytest.fail("POSIX 平台不应调用 icacls"))
    crypto._restrict_key_file(key)


# ---------------------------------------------------------------------------
# F-14 站内通知缓冲的测试隔离（顺序对：A 写入 → B 必须读空）
# ---------------------------------------------------------------------------

def test_notifier_isolation_a_writes(sandbox):
    """隔离对前半：写入一条通知，留给下一个测试当'污染物'。"""
    notifier.append({"event": "isolation-probe", "timestamp": 1.0})
    assert notifier.get_all() != []


def test_notifier_isolation_b_starts_empty(sandbox):
    """隔离对后半（F-14）：上一个测试写的通知不得泄漏进本测试。"""
    assert notifier.get_all() == []


# ---------------------------------------------------------------------------
# F-27 回滚无操作显式化
# ---------------------------------------------------------------------------

def test_rollback_noop_returns_explicit_message(conn):
    """目标版本内容 == 当前内容：显式"无需回滚"，且不新增历史行。"""
    aid = db.create_article(conn, "标题", "同一份内容")
    versions.capture(conn, dict(db.get_article(conn, aid)), change_kind="edit")
    vid = versions.list_versions(conn, aid)[0]["id"]
    before = len(versions.list_versions(conn, aid))

    ok, msg = versions.rollback(conn, vid)

    assert ok is True
    assert "无需回滚" in msg
    assert len(versions.list_versions(conn, aid)) == before


def test_rollback_restores_tags_when_only_tags_differ(conn):
    """只改了标签时回滚不是 no-op：短路比对必须含 tags，否则标签永远回不去。"""
    aid = db.create_article(conn, "标题", "同一份内容", tags="旧标签")
    versions.capture(conn, dict(db.get_article(conn, aid)), change_kind="edit")
    vid = versions.list_versions(conn, aid)[0]["id"]
    db.update_article(conn, aid, tags="新标签")

    ok, msg = versions.rollback(conn, vid)

    assert ok is True
    assert "无需回滚" not in msg, "tags 有差异时不应短路为无需回滚"
    assert db.get_article(conn, aid)["tags"] == "旧标签"
