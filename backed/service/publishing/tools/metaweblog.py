# -*- coding: utf-8 -*-
"""博客园 (cnblogs) MetaWeblog API 通用客户端。

MetaWeblog API 是 XML-RPC 协议，Python 标准库 xmlrpc.client 即可调用，零外部依赖。
博客园是目前唯一仍开放 MetaWeblog 的中文技术博客平台。

接口文档: https://rpc.cnblogs.com/metaweblog/
使用方式：
    cli = MetaWeblogClient(
        endpoint="https://rpc.cnblogs.com/metaweblog/{博客名}",
        username="your_user",
        password="your_access_token",   # 博客园后台 -> 设置 -> MetaWeblog -> 访问令牌
    )
    post_id = cli.new_post("标题", "<p>HTML 内容</p>", categories=["技术"], mt_keywords="Python,自动化")
    url = cli.get_post_url(post_id)
"""

import xmlrpc.client
from base64 import b64decode
from typing import Optional


class MetaWeblogClient:
    """博客园 MetaWeblog XML-RPC 客户端（零依赖，标准库实现）。"""

    def __init__(self, endpoint: str, username: str, password: str):
        self.endpoint = endpoint
        self.username = username
        self.password = password
        self._server = xmlrpc.client.ServerProxy(endpoint)

    # ---------------- 文章操作 ----------------

    def new_post(self, title: str, description: str, categories: list = None,
                 mt_keywords: str = "", publish: bool = True) -> str:
        """创建新文章。返回 post_id。HTML 或 Markdown 皆可。"""
        post_struct = _build_post_struct(title, description, categories, mt_keywords)
        return self._server.metaWeblog.newPost("", self.username, self.password, post_struct, publish)

    def edit_post(self, post_id: str, title: str, description: str,
                  categories: list = None, mt_keywords: str = "") -> bool:
        """更新已发布文章。返回 True/False。"""
        post_struct = _build_post_struct(title, description, categories, mt_keywords)
        return self._server.metaWeblog.editPost(
            post_id, self.username, self.password, post_struct, True)

    def delete_post(self, post_id: str) -> bool:
        """删除文章。返回 True/False。"""
        return self._server.metaWeblog.deletePost(
            "", post_id, self.username, self.password, True)

    def get_post(self, post_id: str) -> dict:
        """获取文章详情。返回 dict，无则返回 {}。"""
        try:
            return self._server.metaWeblog.getPost(post_id, self.username, self.password)
        except Exception:
            return {}

    def get_recent_posts(self, count: int = 10) -> list:
        """获取最近 N 篇文章列表。返回 [{post_id, title, description, link, dateCreated, ...}]"""
        try:
            return self._server.metaWeblog.getRecentPosts(
                "", self.username, self.password, count)
        except Exception:
            return []

    def get_post_url(self, post_id: str) -> Optional[str]:
        """获取文章发布 URL。"""
        post = self.get_post(post_id)
        return post.get("link") or post.get("permaLink")

    # ---------------- 分类 ----------------

    def get_categories(self) -> list:
        """获取博客分类列表。返回 [{categoryId, categoryName, parentId}]。"""
        try:
            return self._server.metaWeblog.getCategories("", self.username, self.password)
        except Exception:
            return []

    # ---------------- 媒体上传 ----------------

    def upload_image(self, name: str, mime_type: str, data: bytes) -> str:
        """上传图片/文件。返回图片 URL。URL 为空时说明上传失败。"""
        BIT = xmlrpc.client.Binary(data)
        result = self._server.metaWeblog.newMediaObject(
            "", self.username, self.password,
            {"name": name, "type": mime_type, "bits": BIT})
        return result.get("url", "")

    def upload_image_b64(self, name: str, mime_type: str, b64_data: str) -> str:
        """上传 base64 编码的图片。支持 data:image/png;base64,... 前缀。"""
        raw = b64decode(b64_data.split(",", 1)[-1])
        return self.upload_image(name, mime_type or _guess_mime(name), raw)


def _build_post_struct(title: str, description: str, categories: list = None,
                       mt_keywords: str = "") -> dict:
    """构建 MetaWeblog post 结构。"""
    post = {
        "title": title or "",
        "description": description or "",
        "mt_keywords": mt_keywords or "",
    }
    if categories:
        post["categories"] = [str(c) for c in categories]
    return post


def _guess_mime(name: str) -> str:
    """按文件名猜测 MIME 类型。"""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
    }.get(ext, "image/png")
