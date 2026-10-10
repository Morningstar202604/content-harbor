# -*- coding: utf-8 -*-
"""AI 写稿 / Provider 管理 / AIGC 合规门禁端点。"""

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..deps import get_hub

router = APIRouter()


class AIWriteIn(BaseModel):
    topic: str
    style: str = ""
    words: int = 2000
    tags_hint: str = ""
    publish_to: Optional[List[str]] = None
    model: str = ""
    preferred_provider: str = ""


class AIModelIn(BaseModel):
    model: str = ""
    preferred_provider: str = ""


class AIRewriteIn(BaseModel):
    instruction: str
    publish_to: Optional[List[str]] = None
    model: str = ""
    preferred_provider: str = ""


class AIWriteTemplateIn(BaseModel):
    topic: str
    template: str = ""
    style: str = ""
    words: int = 2000
    tags_hint: str = ""


# ---- AI 写稿 ----

@router.post("/ai/write")
def ai_write(body: AIWriteIn):
    return get_hub().ai_write(body.topic, body.style, body.words,
                        body.tags_hint, body.publish_to,
                        model=body.model or None,
                        preferred_provider=body.preferred_provider or None)


@router.post("/ai/write-template")
def ai_write_template(body: AIWriteTemplateIn):
    """用预置模板 AI 写文章。"""
    art = get_hub().ai_write_with_template(
        body.topic, body.template, style=body.style, words=body.words, tags_hint=body.tags_hint)
    aid = get_hub().create(art["title"], art["content_md"],
                           summary=art["summary"], tags=art["tags"],
                           source="ai", ai_model=art.get("ai_model", ""))
    return {"id": aid, "title": art["title"], "summary": art["summary"]}


@router.get("/ai/status")
def ai_status():
    ready = get_hub().ai_ready()
    providers = []
    try:
        from service.publishing import providers as prov_mod
        providers = prov_mod.list_providers()
    except Exception:
        pass
    return {"ready": ready, "providers": providers}


@router.get("/ai/providers")
def ai_providers():
    """列出所有可用 Provider + 模型。"""
    from service.publishing import providers as prov_mod
    return prov_mod.list_available_providers()


@router.get("/ai/templates")
def ai_templates():
    """列出所有可用写作模板。"""
    return get_hub().list_ai_templates()


@router.get("/ai/gate")
def ai_gate():
    """AIGC 合规门禁状态：开关、审查模型、高危词数、最近拒绝。"""
    from service.publishing import gate as g
    snap = {"enabled": g.is_enabled(),
            "review_model": g._cfg("REVIEW_MODEL", "").strip() or "(未配置，走本地 heuristic)",
            "dangerous_terms": len(g.DANGEROUS_PATTERNS),
            "human_review_gate": "AI 源内容禁止直接 publish，须 draft_only + 人工确认"}
    try:
        from service.publishing import db
        rows = db.list_failed_jobs(get_hub().conn, type_="publish", limit=50)
        denied = [dict(r) for r in rows if any(
            k in (r["message"] or "") for k in ("门禁", "高危", "人工确认", "合规"))]
        snap["recent_denied"] = denied[:10]
    except Exception:
        snap["recent_denied"] = []
    return snap
