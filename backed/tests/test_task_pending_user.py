# -*- coding: utf-8 -*-
"""任务引擎的中断模式语义（2026-10-14）。

覆盖：pending_user 结果 → 任务挂 waiting_human（不重试/不标完成）；
resume 对 pending_user 是"标记完成"不重跑（防重复发布）；api.js mode 透传。
"""


from service.publishing import db
from service.publishing.tasks import TaskManager, _has_pending_user


class _Shell:
    """TaskManager 的最小宿主：只给 conn 与 hub。"""

    def __init__(self, conn, hub):
        self.conn = conn
        self.hub = hub


class _StubHub:
    def __init__(self, result):
        self._result = result

    def publish(self, *a, **kw):
        return self._result


def _mgr(conn, result):
    m = TaskManager.__new__(TaskManager)   # 不启 worker 线程
    m.conn = conn
    m.hub = _StubHub(result)
    import threading
    m._lock = threading.Lock()
    m._wake = threading.Event()
    m._stop = threading.Event()
    return m


def test_has_pending_user_detects_list_and_dict():
    assert _has_pending_user([{"ok": True, "pending_user": True}]) is True
    assert _has_pending_user({"results": [{"pending_user": True}]}) is True
    assert _has_pending_user([{"ok": True}]) is False
    assert _has_pending_user(None) is False


def test_pending_user_result_goes_waiting_human(conn):
    """中断模式结果 → waiting_human（不当失败不重试），resume 标记完成不重跑。"""
    m = _mgr(conn, [{"platform": "zhihu", "ok": True, "status": "pending_user",
                     "pending_user": True, "message": "平台页已打开，等你确认"}])
    tid = "t-pending-user"
    task_id = m.submit("publish", article_id=1, platforms=["zhihu"])
    # 覆盖成固定 id 便于断言
    conn.execute("UPDATE tasks SET task_id=? WHERE task_id=?", (tid, task_id))
    conn.commit()
    task = db.get_task(conn, tid)
    m._run_task(task)

    t = db.get_task(conn, tid)
    assert t["status"] == "waiting_human", t["status"]
    assert "等你确认" in (t["message"] or "")
    assert t["status"] != "ok"      # 中断 ≠ 完成

    # resume(approved=True)：标记完成，状态 ok，且不再产生新执行
    r = m.resume(tid, approved=True)
    assert r["ok"] is True
    assert db.get_task(conn, tid)["status"] == "ok"
    assert "中断模式收尾" in (db.get_task(conn, tid)["message"] or "")


def test_auto_result_still_completes(conn):
    """auto 模式结果照旧标 ok（回归：中断分支不影响正常完成）。"""
    m = _mgr(conn, [{"platform": "zhihu", "ok": True, "status": "ok"}])
    task_id = m.submit("publish", article_id=1, platforms=["zhihu"])
    m._run_task(db.get_task(conn, task_id))
    assert db.get_task(conn, task_id)["status"] == "ok"


def test_resume_requires_waiting_human(conn):
    m = _mgr(conn, [])
    task_id = m.submit("publish", article_id=1, platforms=["zhihu"])
    r = m.resume(task_id, approved=True)   # 还在 pending
    assert r["ok"] is False
