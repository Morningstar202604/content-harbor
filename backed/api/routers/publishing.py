# -*- coding: utf-8 -*-
"""发布 / 更新 / 同步端点 + 统一任务查询。"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..deps import get_hub

router = APIRouter()


class PublishIn(BaseModel):
    platforms: List[str]
    account: str = "default"
    draft_only: bool = False
    live: bool = False
    settings: Optional[Dict[str, Dict]] = None


class UpdateIn(BaseModel):
    platforms: Optional[List[str]] = None
    account: str = "default"


class ResumeIn(BaseModel):
    approved: bool = True
    note: str = ""


# ---- 发布 / 更新 / 同步 ----

@router.post("/articles/{aid}/publish")
def publish(aid: int, body: PublishIn):
    """异步发布：提交到统一任务引擎，立即返回 task_id。"""
    task_id = get_hub().tasks.submit("publish", article_id=aid, platforms=body.platforms,
                               account=body.account, draft_only=body.draft_only,
                               settings=body.settings)
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}


@router.post("/articles/{aid}/update")
def update(aid: int, body: UpdateIn):
    """异步原地更新：提交任务，轮询 GET /tasks/{task_id}。"""
    task_id = get_hub().tasks.submit("update", article_id=aid, platforms=body.platforms,
                               account=body.account)
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}


@router.post("/sync/pending")
def sync_pending(body: Optional[UpdateIn] = None):
    """异步同步扇出：把所有待更新实例提交一个 sync 任务。"""
    account = body.account if body else "default"
    task_id = get_hub().tasks.submit("sync", account=account)
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}


# ---- 统一任务查询 / 恢复 ----

@router.get("/tasks")
def tasks_list(limit: int = 50, kind: str = None, status: str = None):
    """任务列表：按 kind/status 过滤，默认返回最近 50 条。"""
    return get_hub().tasks.list(limit=limit, kind=kind, status=status)


@router.get("/tasks/{task_id}")
def tasks_detail(task_id: str):
    """查询任意任务状态：pending / running / ok / failed / waiting_human。"""
    import json
    t = get_hub().tasks.get(task_id)
    if not t:
        raise HTTPException(404, "任务不存在或已过期")
    t = dict(t)
    try:
        t["result"] = json.loads(t.get("result") or "{}")
    except Exception:
        t["result"] = {}
    try:
        t["platforms"] = json.loads(t.get("platforms") or "[]")
    except Exception:
        t["platforms"] = []
    return t


@router.post("/tasks/{task_id}/resume")
def tasks_resume(task_id: str, body: Optional[ResumeIn] = None):
    """恢复 waiting_human 任务：approved=true 重新执行；false 标记放弃。"""
    approved = body.approved if body else True
    r = get_hub().tasks.resume(task_id, approved=approved)
    if not r.get("ok"):
        raise HTTPException(409, r.get("error", "恢复失败"))
    return r
