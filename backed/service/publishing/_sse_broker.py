# -*- coding: utf-8 -*-
"""SSE 客户端管理：订阅、注销、广播。支持多个前端长连接同时在线。"""

import queue
import threading

# 每个连接一个 Queue（maxsize=64，满了就丢弃事件，防慢客户端拖垮服务端）
_clients: set[queue.Queue] = set()
_lock = threading.Lock()


def subscribe() -> queue.Queue:
    """注册一个 SSE 客户端，返回 Queue，新事件会推入其中。"""
    q = queue.Queue(maxsize=64)
    with _lock:
        _clients.add(q)
    return q


def unsubscribe(q: queue.Queue):
    """注销 SSE 客户端（前端断开连接时调用）。"""
    with _lock:
        _clients.discard(q)


def broadcast(event: dict):
    """把事件推送到所有已注册的 SSE 客户端。满了就丢弃（不阻塞 emit）。"""
    with _lock:
        clients = list(_clients)
    for q in clients:
        try:
            q.put_nowait(event)
        except queue.Full:
            pass   # 客户端来不及消费就跳过


def client_count() -> int:
    """当前活跃 SSE 连接数。"""
    with _lock:
        return len(_clients)
