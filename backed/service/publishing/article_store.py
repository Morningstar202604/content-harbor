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
        """编辑文章（仅写库，不带待同步计数——那部分由 Hub 封装层负责）。

        旧实现最后一行 `db.get_pending_updates(self.conn, article_id)` 传参个数与
        `db.get_pending_updates(conn)` 不匹配，一旦真被调就直接 TypeError；
        而 Hub.edit 自己写了实现并不委托，所以这个 bug 一直隐死在代码里。
        现在改成：先快照版本、再写库，返回值给调用方自取。
        """
        art = db.get_article(self.conn, article_id)
        if not art:
            raise ValueError(f"文章不存在: {article_id}")
        ver_capture(self.conn, dict(art))
        return db.update_article(self.conn, article_id, **kw)

    def get(self, article_id):
        return db.get_article(self.conn, article_id)

    def list(self, status=None, limit=100):
        return db.list_articles(self.conn, status=status, limit=limit)

    def search(self, keyword):
        return db.search_articles(self.conn, keyword)

    def accounts(self):
        return db.list_accounts(self.conn)
