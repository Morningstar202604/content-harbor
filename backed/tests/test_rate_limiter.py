# -*- coding: utf-8 -*-
"""限流中间件回归——此前零覆盖，却是安全边界上的关键一环。

抓住的真实缺陷：_get_client_ip 无条件采信 X-Forwarded-For，而该头由客户端
自由填写。任何人每请求换一个 XFF 就拿到一个全新令牌桶，限流形同虚设。
本轮改为：只有对端本身受信（本机回环 / TRUSTED_NETS）时才采信代理头，
判定复用 api/hub.py 的既有约定，不另造一套。
"""

import pytest
from starlette.requests import Request

from middleware import rate_limiter as rl
from middleware.rate_limiter import InMemoryRateLimiter, RateLimitMiddleware


def mk(path="/api/hub/articles", headers=None, client=("1.2.3.4", 5000)):
    return Request({
        "type": "http", "method": "GET", "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": client, "query_string": b"", "scheme": "http",
        "server": ("x", 80), "root_path": "",
    })


# ---------------- 真实客户端 IP ----------------

def test_direct_connection_uses_peer_ip():
    assert RateLimitMiddleware._get_client_ip(mk()) == "1.2.3.4"


def test_spoofed_forwarded_for_is_ignored_on_direct(monkeypatch):
    """回归核心：直连时伪造 XFF 不得改变限流键，否则限流可被一键绕过。"""
    monkeypatch.delenv("TRUSTED_NETS", raising=False)
    req = mk(headers={"X-Forwarded-For": "9.9.9.9"})
    assert RateLimitMiddleware._get_client_ip(req) == "1.2.3.4"


def test_spoofed_real_ip_is_ignored_on_direct(monkeypatch):
    monkeypatch.delenv("TRUSTED_NETS", raising=False)
    req = mk(headers={"X-Real-IP": "8.8.8.8"})
    assert RateLimitMiddleware._get_client_ip(req) == "1.2.3.4"


def test_trusted_proxy_forwarded_for_is_used(monkeypatch):
    """经本机反向代理时，XFF 仍要能正确解析出真实客户端。"""
    monkeypatch.delenv("TRUSTED_NETS", raising=False)
    req = mk(headers={"X-Forwarded-For": "8.8.8.8, 10.0.0.1"},
             client=("127.0.0.1", 1))
    assert RateLimitMiddleware._get_client_ip(req) == "8.8.8.8"


def test_trusted_proxy_real_ip_is_used(monkeypatch):
    monkeypatch.delenv("TRUSTED_NETS", raising=False)
    req = mk(headers={"X-Real-IP": "7.7.7.7"}, client=("127.0.0.1", 1))
    assert RateLimitMiddleware._get_client_ip(req) == "7.7.7.7"


def test_extra_trusted_net_enables_proxy_headers(monkeypatch):
    monkeypatch.setenv("TRUSTED_NETS", "10.1.0.0/16")
    req = mk(headers={"X-Forwarded-For": "8.8.8.8"}, client=("10.1.2.3", 1))
    assert RateLimitMiddleware._get_client_ip(req) == "8.8.8.8"
    # 不在网段内的对端仍然不可信
    req2 = mk(headers={"X-Forwarded-For": "8.8.8.8"}, client=("192.168.1.1", 1))
    assert RateLimitMiddleware._get_client_ip(req2) == "192.168.1.1"


def test_malformed_trusted_nets_does_not_break(monkeypatch):
    """配错的网段必须被忽略，不能让限流整体抛异常。"""
    monkeypatch.setenv("TRUSTED_NETS", "not-an-ip,10.0.0.0/8")
    req = mk(headers={"X-Forwarded-For": "8.8.8.8"}, client=("127.0.0.1", 1))
    assert RateLimitMiddleware._get_client_ip(req) == "8.8.8.8"


def test_unparsable_peer_is_not_trusted(monkeypatch):
    monkeypatch.delenv("TRUSTED_NETS", raising=False)
    req = mk(headers={"X-Forwarded-For": "8.8.8.8"}, client=("not-an-ip", 1))
    assert RateLimitMiddleware._get_client_ip(req) == "not-an-ip"


def test_missing_client_falls_back_to_unknown(monkeypatch):
    monkeypatch.delenv("TRUSTED_NETS", raising=False)
    req = mk(headers={"X-Forwarded-For": "8.8.8.8"}, client=None)
    assert RateLimitMiddleware._get_client_ip(req) == "unknown"


# ---------------- 跳过路径 ----------------

@pytest.mark.parametrize("path,expected", [
    ("/health", True),
    ("/ping", True),
    ("/metrics", True),
    ("/docs", True),
    ("/redoc", True),
    ("/openapi.json", True),
    ("/api/hub/articles", False),
    ("/api/hub/tasks", False),
])
def test_should_skip(path, expected):
    assert RateLimitMiddleware._should_skip(mk(path=path)) is expected


# ---------------- 令牌桶 ----------------

def test_bucket_allows_burst_then_limits():
    lim = InMemoryRateLimiter()
    cap = lim._capacity
    allowed = [lim.is_allowed("k")[0] for _ in range(cap + 5)]
    assert allowed[:cap] == [True] * cap
    assert allowed[cap] is False


def test_bucket_keys_are_independent():
    lim = InMemoryRateLimiter()
    for _ in range(lim._capacity):
        lim.is_allowed("a")
    assert lim.is_allowed("a")[0] is False
    assert lim.is_allowed("b")[0] is True


def test_bucket_refills_over_time(monkeypatch):
    """令牌桶必须随时间补充，否则限流一旦触发就永久锁死。"""
    import middleware.rate_limiter as mod
    base = [1000.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: base[0])

    lim = InMemoryRateLimiter()
    for _ in range(lim._capacity):
        lim.is_allowed("k")
    assert lim.is_allowed("k")[0] is False

    base[0] += 60.0            # 推进一分钟
    assert lim.is_allowed("k")[0] is True


def test_bucket_resets_on_reset():
    lim = InMemoryRateLimiter()
    for _ in range(lim._capacity):
        lim.is_allowed("k")
    assert lim.is_allowed("k")[0] is False
    lim.reset()
    assert lim.is_allowed("k")[0] is True


def test_stats_shape():
    lim = InMemoryRateLimiter()
    allowed, stats = lim.is_allowed("k")
    for key in ("limit", "remaining", "reset", "retry_after"):
        assert key in stats
    assert stats["limit"] == lim._capacity
    assert stats["retry_after"] == (0 if allowed else 1)


def test_remaining_never_negative():
    lim = InMemoryRateLimiter()
    for _ in range(lim._capacity * 3):
        _, stats = lim.is_allowed("k")
        assert stats["remaining"] >= 0


def test_module_limiter_is_resettable():
    rl._limiter.reset()
    assert rl._limiter.is_allowed("fresh-key")[0] is True