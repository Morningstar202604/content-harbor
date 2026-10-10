# -*- coding: utf-8 -*-
"""站内通知环形缓冲（内存，最近 200 条，跨线程安全）。"""

import threading
from collections import deque

_notifications = deque(maxlen=200)
_notifications_lock = threading.Lock()


def append(event: dict):
    """写入一条通知。"""
    with _notifications_lock:
        _notifications.append(event)


def get_all():
    """返回全部通知的副本。"""
    with _notifications_lock:
        return list(_notifications)


def get_since(since: float = None, limit: int = 50):
    """返回 since 之后的通知（最多 limit 条）。"""
    with _notifications_lock:
        items = list(_notifications)
    if since is not None:
        items = [i for i in items if i.get("timestamp", 0) > since]
    return items[-limit:]


def clear():
    """清空通知缓冲。"""
    with _notifications_lock:
        _notifications.clear()
