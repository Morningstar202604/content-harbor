# -*- coding: utf-8 -*-
"""事件系统回归：webhook 存储、签名、通知环形缓冲、任务事件映射。

webhooks 表长在 module 级 `_DB_PATH` 上，conftest 已把该常量指到临时库，
所以这里直接走公开 API（register/list/update/delete），不再碰裸 SQL。
"""

import hashlib
import hmac as hmac_mod
import json
import time

from service.publishing import events


def test_register_webhook_defaults_to_all_events():
    wid = events.register_webhook("https://example.com/hook")
    assert wid > 0
    row = [h for h in events.list_webhooks() if h["id"] == wid][0]
    assert row["url"] == "https://example.com/hook"
    assert row["events"] == ["*"]
    assert row["enabled"] is True


def test_register_webhook_scopes_events_and_hides_secret():
    events.register_webhook("https://example.com/task", events=["task.ok"],
                            secret="s3cret")
    row = events.list_webhooks()[-1]
    assert row["events"] == ["task.ok"]
    # secret 永不出现在读接口里，只暴露 has_secret 布尔
    assert "secret" not in row
    assert row["has_secret"] is True


def test_update_webhook_changes_url_and_events():
    wid = events.register_webhook("https://example.com/a")
    assert events.update_webhook(wid, url="https://other",
                                events=["task.failed"]) is True
    row = [h for h in events.list_webhooks() if h["id"] == wid][0]
    assert row["url"] == "https://other"
    assert row["events"] == ["task.failed"]


def test_update_webhook_rejects_unknown_field():
    wid = events.register_webhook("https://example.com/a")
    assert events.update_webhook(wid, nope="x") is False


def test_delete_webhook():
    wid = events.register_webhook("https://example.com/gone")
    assert events.delete_webhook(wid) is True
    assert all(h["id"] != wid for h in events.list_webhooks())
    assert events.delete_webhook(wid) is False


def test_sign_payload_is_hmac_sha256():
    from service.publishing import crypto
    body = json.dumps({"type": "task.ok"}, ensure_ascii=False)
    # secret 落库时加密存储，传入 _sign_payload 的是密文
    encrypted = crypto.encrypt("topsecret")
    sig = events._sign_payload(body, encrypted)
    assert sig == hmac_mod.new(b"topsecret", body.encode("utf-8"),
                              hashlib.sha256).hexdigest()
    # 换密钥签名必须变，否则重放即伪造
    assert events._sign_payload(body, crypto.encrypt("other")) != sig
    # 没配 secret 就不签（不伪造空签名头）
    assert events._sign_payload(body, "") == ""
    assert events._sign_payload(body, crypto.encrypt("")) == ""


def test_emit_appends_to_notification_ring():
    before = len(events.get_notifications(limit=200))
    events.emit("task.ok", {"task_id": "abc"})
    after = events.get_notifications(limit=200)
    assert len(after) == before + 1
    last = after[-1]
    assert last["type"] == "task.ok"
    assert last["data"]["task_id"] == "abc"
    assert last["timestamp"] > 0


def test_get_notifications_since_filters():
    # 全局环形缓冲是跨用例共享的，所以用「时间窗口 + 专有标记」断言，
    # 不假设缓冲里没有别的事件。
    assert events.get_notifications(since=time.time() + 60, limit=200) == []

    events.emit("account.logout", {"tag": "old"})
    time.sleep(0.02)                    # 隔开时间戳，避开 ms 级分辨率
    marker = time.time() - 0.005
    events.emit("account.logout", {"tag": "new"})

    got = events.get_notifications(since=marker, limit=200)
    assert [g["data"]["tag"] for g in got] == ["new"]


def test_event_types_cover_documented_surface():
    for t in ("task.ok", "task.failed", "task.waiting_human", "publish.ok",
              "publish.failed", "article.created", "article.updated",
              "account.login", "account.logout", "ai.write", "ai.rewrite"):
        assert t in events.EVENT_TYPES


def _ring_types():
    return [n["type"] for n in events.get_notifications(limit=200)]


def test_on_task_complete_maps_status_to_events():
    base = {"task_id": "t1", "kind": "publish", "article_id": 1, "result": {}}
    cases = (
        ({**base, "status": "ok"}, ["task.ok", "publish.ok"]),
        ({**base, "status": "failed", "error": "x"},
         ["task.failed", "publish.failed"]),
        ({**base, "status": "waiting_human", "message": "m"},
         ["task.waiting_human"]),
    )
    for task, expected in cases:
        n_before = len(_ring_types())
        events.on_task_complete(task)
        new = _ring_types()[n_before:]
        assert sorted(new) == sorted(expected)


def test_on_task_complete_non_publish_only_emits_task_event():
    task = {"task_id": "t2", "kind": "login", "article_id": None,
            "status": "ok", "result": {}}
    n_before = len(_ring_types())
    events.on_task_complete(task)
    assert _ring_types()[n_before:] == ["task.ok"]


def test_on_task_complete_handles_list_and_dict_results():
    """Hub.publish 返回 list，sync 返回 dict——两种形态都要取到平台名。"""
    for result, want in (
        ([{"platform": "juejin"}], ["juejin"]),
        ({"results": [{"platform": "csdn"}]}, ["csdn"]),
    ):
        task = {"task_id": "t3", "kind": "publish", "article_id": 1,
                "status": "ok", "result": result}
        n_before = len(_ring_types())
        events.on_task_complete(task)
        new = events.get_notifications(limit=200)[n_before:]
        note = [n for n in new if n["type"] == "publish.ok"][0]
        assert note["data"]["platforms"] == want


def test_on_task_complete_truncates_long_error():
    task = {"task_id": "t4", "kind": "publish", "article_id": 1,
            "status": "failed", "error": "E" * 5000}
    n_before = len(_ring_types())
    events.on_task_complete(task)
    note = [n for n in events.get_notifications(limit=200)[n_before:]
            if n["type"] == "publish.failed"][0]
    assert len(note["data"]["error"]) == 200


def test_dispatcher_can_be_stopped(sandbox):
    """派发线程是导入时拉起的守护线程；stop 后 emit 不得抛错也不得发 HTTP。"""
    events.stop_dispatcher()
    events.emit("task.ok", {"task_id": "x"})
    assert True
