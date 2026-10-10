# -*- coding: utf-8 -*-
"""标签治理端点。"""

from fastapi import APIRouter, HTTPException

from ..deps import get_hub

router = APIRouter()


@router.get("/tags")
def tags_list(limit: int = 50, category: str = None):
    from service.publishing.tags import list_tags
    return list_tags(get_hub().conn, limit=limit, category=category or None)


@router.get("/tags/trending")
def tags_trending(limit: int = 10):
    from service.publishing.tags import trending
    return trending(get_hub().conn, limit=limit)


@router.post("/tags/sync")
def tags_sync():
    """从 articles 重建标签统计。"""
    from service.publishing.tags import sync_from_articles
    return sync_from_articles(get_hub().conn)


@router.post("/tags/rename")
def tags_rename(old: str, new: str):
    from service.publishing.tags import rename_tag
    return rename_tag(get_hub().conn, old, new)


@router.post("/tags/merge")
def tags_merge(_from: str = "", to: str = ""):
    """合并标签：_from -> to（_from 被合并消失，to 保留）。"""
    from service.publishing.tags import merge_tags
    if not _from or not to:
        raise HTTPException(422, "from 和 to 必填")
    return merge_tags(get_hub().conn, _from, to)


@router.post("/tags/alias")
def tags_alias(alias: str = "", canonical: str = ""):
    """添加标签别名：alias 出现时自动替换成 canonical。"""
    from service.publishing.tags import add_alias
    if not alias or not canonical:
        raise HTTPException(422, "alias 和 canonical 必填")
    return add_alias(get_hub().conn, alias, canonical)


@router.post("/tags/suggest")
def tags_suggest(title: str = "", content_md: str = ""):
    """根据标题+正文推荐 3-5 个标签。"""
    from service.publishing.tags import suggest_for_article
    return {"tags": suggest_for_article(get_hub().conn, title or "", content_md or "")}
