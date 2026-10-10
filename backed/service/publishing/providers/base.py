# -*- coding: utf-8 -*-
"""外部工具 provider 的标准接口。"""


class ProviderResult:
    """外部工具调用结果。"""

    def __init__(self, ok: bool, platform: str, post_id: str = "",
                 post_url: str = "", edit_url: str = "",
                 draft_only: bool = False, error: str = "",
                 raw: dict = None):
        self.ok = ok
        self.platform = platform
        self.post_id = post_id
        self.post_url = post_url
        self.edit_url = edit_url
        self.draft_only = draft_only
        self.error = error
        self.raw = raw or {}

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "platform": self.platform,
            "post_id": self.post_id,
            "post_url": self.post_url,
            "edit_url": self.edit_url,
            "draft_only": self.draft_only,
            "error": self.error,
        }


class ProviderError(Exception):
    pass


class PublishProvider:
    """外部工具接口基类：各平台成熟工具封装成统一语义。"""

    platform_id: str = ""
    tool_name: str = ""
    tool_url: str = ""

    def is_available(self) -> bool:
        """检测外部工具是否已安装并可用。"""
        return False

    def check_auth(self) -> bool:
        """检测外部工具是否已登录。"""
        return False

    def publish(self, article: dict, options: dict = None) -> ProviderResult:
        """发布文章。返回 ProviderResult。"""
        raise NotImplementedError

    def update(self, post_id: str, article: dict, options: dict = None) -> ProviderResult:
        """更新文章。返回 ProviderResult。"""
        raise NotImplementedError

    def list_articles(self, limit: int = 50) -> list:
        """列出平台上的文章。"""
        return []
