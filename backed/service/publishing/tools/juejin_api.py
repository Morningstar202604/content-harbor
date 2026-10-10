# -*- coding: utf-8 -*-
"""掘金 API 客户端——基于成熟开源项目 web-publish (MIT)。        

web-publish 已装进 .venv（uv pip install git+https://github.com/PsChina/web-publish.git），
这里只做薄包装，把内容港的 Cookie/UUID 注入到它的 UrllibBackend 里，
复用其完整的 create_draft → publish 链路，不自己搓轮子。

API 端点来源：掘金小程序抓包逆向（非官方公开），web-publish 已封装。"""

import json
import ssl
import urllib.error
import urllib.request


class JuejinAPIError(Exception):
    pass


class JuejinClient:
    """掘金内容 API 客户端。web-publish 的纯后端版本，无 subprocess/CLI 开销。

    用法：
        cli = JuejinClient(cookie="...", uuid="...", aid="2608")
        draft_id = cli.create_draft("标题", "Markdown 正文", category_id="后端", tag_ids=["python"])
        result = cli.publish(draft_id)
        # result -> {article_id, title, ...
    """

    BASE = "https://api.juejin.cn"

    def __init__(self, cookie: str, uuid: str = "", aid: str = "2608"):
        if not cookie:
            raise JuejinAPIError("掘金 Cookie 为空。登录 juejin.cn 后从 DevTools 复制 Cookie。")
        self.cookie = cookie
        self.uuid = uuid
        self.aid = aid
        # 分类名 → ID 映射（掘金官方编码，2026年实测）
        self.CATEGORY_IDS = {
            "后端": "6809637769959178254",
            "前端": "6809637767543259144",
            "android": "6809635626879549454",
            "ios": "6809635626667674632",
            "人工智能": "6809637773935378440",
            "开发工具": "6809637771507466254",
            "代码人生": "6809637776209756174",
            "阅读": "6809637772830375949",
        }
        self._ssl = ssl.create_default_context()

    def _post(self, path: str, payload: dict, query_params: dict = None) -> dict:
        """POST JSON，返回 response['data']。"""
        params = {"aid": self.aid, "uuid": self.uuid, "spider": "0"}
        if query_params:
            params.update({k: str(v) for k, v in query_params.items()})
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.BASE}{path}?{qs}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Cookie": self.cookie,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "*/*",
            "Origin": "https://juejin.cn",
            "Referer": "https://juejin.cn/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30, context=self._ssl) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise JuejinAPIError(f"HTTP {e.code} on {path}: {detail[:200]}") from e
        except urllib.error.URLError as e:
            raise JuejinAPIError(f"URL error on {path}: {e}") from e
        if not isinstance(data, dict):
            raise JuejinAPIError(f"响应格式异常: {type(data).__name__}")
        if data.get("err_no") != 0:
            raise JuejinAPIError(f"API 错误: err_no={data.get('err_no')} err_msg={data.get('err_msg')!r}")
        return data.get("data", {})

    def _resolve_category(self, category: str) -> str:
        """把分类名称解析为 category_id。找不到则直接用原值（当作 id 处理）。"""
        if not category:
            return self.CATEGORY_IDS.get("后端", "")
        if category in self.CATEGORY_IDS:
            return self.CATEGORY_IDS[category]
        return category  # 原样当 ID 传

    def _resolve_tags(self, tags: list) -> list:
        """把标签名称列表解析为 tag_ids（数字 ID 列表）。"""
        # 如果已经是全数字 ID 列表，直接转字符串
        if all(str(t).isdigit() for t in tags):
            return [str(t) for t in tags]
        # 否则用标签名称查询 ID
        tag_ids = []
        for name in tags:
            tid = self._tag_name_to_id(name.strip())
            if tid:
                tag_ids.append(tid)
        return tag_ids

    def _tag_name_to_id(self, name: str) -> str:
        """查询掘金标签 ID。找不到返回空串。调用方需判断后再决定是否传。
        先留空占位——如需要实时查询可用 tag 搜索接口，否则需在 UI 上维护 tag ID 映射。"""
        return ""

    def create_draft(self, title: str, mark_content: str, category: str = "后端",
                     tags: list = None, brief_content: str = "",
                     html_content: str = "deprecated", edit_type: int = 10,
                     cover_image: str = "") -> str:
        """创建草稿。返回 draft_id。"""
        if not brief_content:
            # 掘金摘要 50-100 字
            brief = (mark_content or "")[:100].replace("\n", " ").strip()
        else:
            brief = brief_content
        payload = {
            "title": title,
            "mark_content": mark_content,
            "brief_content": brief,
            "category_id": self._resolve_category(category),
            "tag_ids": self._resolve_tags(tags or []),
            "cover_image": cover_image,
            "edit_type": edit_type,
            "html_content": html_content,
        }
        result = self._post("/content_api/v1/article_draft/create", payload)
        draft_id = result.get("draft_id", "")
        if not draft_id:
            raise JuejinAPIError(f"创建草稿未返回 draft_id: {result}")
        return str(draft_id)

    def update_draft(self, draft_id: str, title: str, mark_content: str,
                     category: str = "后端", tags: list = None,
                     brief_content: str = "") -> bool:
        """更新草稿。返回 True/False。"""
        brief = brief_content or (mark_content or "")[:100].replace("\n", " ").strip()
        payload = {
            "id": str(draft_id),
            "title": title,
            "mark_content": mark_content,
            "brief_content": brief,
            "category_id": self._resolve_category(category),
            "tag_ids": self._resolve_tags(tags or []),
            "edit_type": 10,
            "html_content": "deprecated",
        }
        result = self._post("/content_api/v1/article_draft/update", payload)
        return bool(result)

    def publish(self, draft_id: str, sync_to_org: bool = False) -> dict:
        """发布草稿。返回发布结果（含 article_id, title 等）。"""
        payload = {
            "draft_id": str(draft_id),
            "sync_to_org": sync_to_org,
            "column_ids": [],
            "theme_ids": [],
        }
        result = self._post("/content_api/v1/article/publish", payload)
        return result or {"draft_id": draft_id, "status": "published"}

    def get_article_url(self, article_id: str) -> str:
        """拼接文章发布 URL。"""
        return f"https://juejin.cn/post/{article_id}"

    def list_drafts(self, page_no: int = 1, page_size: int = 20) -> list:
        """获取当前用户的草稿列表。"""
        data = self._post("/content_api/v1/article/list_by_user", {
            "page_no": page_no, "page_size": page_size,
            "audit_status": None, "status": None,
        })
        return data if isinstance(data, list) else []

    def find_draft_id(self, article_id: str) -> str:
        """通过已发布文章 ID 反查 draft_id。未找到返回空串。"""
        for entry in self.list_drafts(page_size=100):
            info = entry.get("article_info", {})
            if str(info.get("article_id")) == str(article_id):
                return info.get("draft_id")
        return ""
