# -*- coding: utf-8 -*-
"""账号 / 平台端点：登录 / 登出 / 诊断 / 验证码 / 辅助操作 / 刷新。"""


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..deps import get_hub

router = APIRouter()


class LoginIn(BaseModel):
    account: str = "default"
    timeout: int = 600
    on_captcha: str = "handoff"    # handoff=弹验证码交人工；abort=无人值守时直接放弃


class CaptchaIn(BaseModel):
    account: str = "default"
    wait: int = 180


class AssistIn(BaseModel):
    url: str
    timeout: int = 900


# ---- 平台列表 ----

@router.get("/platforms")
def platforms():
    from service.publishing import adapters as _adapters  # noqa: F401
    from service.publishing.adapters.base import ADAPTERS
    return [{"id": a.id, "name": a.name, "needs_browser": a.needs_browser}
            for a in ADAPTERS.values()]


# ---- 账号 ----

@router.get("/accounts")
def accounts():
    return get_hub().accounts()


@router.get("/accounts/{platform}/check")
def check_account(platform: str, account: str = "default"):
    return {"platform": platform, "logined": get_hub().check(platform, account)}


@router.post("/accounts/{platform}/login")
def login(platform: str, body: LoginIn):
    """异步启动登录：提交任务，轮询 GET /tasks/{task_id}。"""
    task_id = get_hub().tasks.submit("login", platforms=[platform], account=body.account)
    return {"task_id": task_id, "platform": platform, "status": "pending",
            "poll": f"/tasks/{task_id}"}


@router.delete("/accounts/{platform}")
def logout(platform: str):
    """清除登录态：删 profile + cookie 快照，账号状态置离线。"""
    r = get_hub().logout(platform)
    return {"ok": True, **r}


@router.get("/accounts/{platform}/diagnose")
def diagnose(platform: str):
    """这个平台该怎么接、验证码怎么过——排查用。"""
    return get_hub().diagnose(platform)


@router.post("/accounts/{platform}/solve-captcha")
def solve_captcha(platform: str, body: CaptchaIn):
    """打开页面就地处理验证码：先半自动试，不行转人工。"""
    return get_hub().solve_captcha(platform, body.account, body.wait)


@router.post("/accounts/{platform}/assist")
def assist_open(platform: str, body: AssistIn):
    """带登录态的内置有头浏览器打开平台页（人工步骤接管）。"""
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(422, "url 必须是 http(s) 地址")
    task_id = get_hub().tasks.submit("assist", platforms=[platform], url=body.url)
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}


@router.post("/refresh/{platform}")
def refresh(platform: str, limit: int = 50):
    """异步抓取平台文章入库。"""
    task_id = get_hub().tasks.submit("refresh", platforms=[platform])
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}
