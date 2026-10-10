# -*- coding: utf-8 -*-
"""文章 CRUD 仓库。

只碰数据库，不启浏览器、不调 AI、不编排任务——可安全单测。
Hub 通过 self.articles 委托到这里。
"""

from service.publishing import db
from service.publishing.versions import capture as ver_capture


class ArticleStore:
    def __init__(self, conn):
        self.conn = conn

    def create(self, title, content_md="", **kw):
        return db.create_article(self.conn, title, content_md=content_md, **kw)

    def edit(self, article_id, **kw):
        art = db.get_article(self.conn, article_id)
        if not art:
            raise ValueError(f"文章不存在: {article_id}")
        ver_capture(self.conn, dict(art))
        db.update_article(self.conn, article_id, **kw)
        db.get_pending_updates(self.conn, article_id)

    def get(self, article_id):
        return db.get_article(self.conn, article_id)

    def list(self, status=None, limit=100):
        return db.list_articles(self.conn, status=status, limit=limit)

    def search(self, keyword):
        return db.search_articles(self.conn, keyword)

    def accounts(self):
        return db.list_accounts(self.conn)
