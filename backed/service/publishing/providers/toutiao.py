# -*- coding: utf-8 -*-
"""头条号 / 头条平台：基于 super-publisher 的外部工具封装。

super-publisher 是 ClawHub（原 OpenClaw）生态的多平台发布工具，覆盖：
  头条号、微信公众号、知乎、掘金、CSDN、博客园、V2EX、小红书等。

安装方式（待接入时执行）：
  pip install super-publisher                # 如果上了 PyPI
  # 或
  pip install git+https://github.com/guanyang/super-publisher.git

使用策略：
  - super-publisher 已安装且已登录 → 直接调
  - 未安装或登录失效 → 回退到原生 Playwright adapter
"""

import shutil
import subprocess
from pathlib import Path

from .base import PublishProvider, ProviderResult, ProviderError
from .registry import register


@register("toutiao")
class ToutiaoProvider(PublishProvider):
    """头条号 provider：复用 super-publisher 的头条模块。"""

    tool_name = "super-publisher"
    tool_url = "https://github.com/guanyang/super-publisher"

    def __init__(self):
        self._cli = None

    def is_available(self) -> bool:
        """检测 super-publisher 是否已安装。"""
        # 方式 1: CLI 入口
        if shutil.which("spub") or shutil.which("super-publisher"):
            self._cli = shutil.which("spub") or shutil.which("super-publisher")
            return True
        # 方式 2: Python 包
        try:
            import super_publisher  # noqa: F401
            return True
        except ImportError:
            pass
        return False

    def check_auth(self) -> bool:
        """检测头条号登录态。"""
        if not self.is_available():
            return False
        if self._cli:
            try:
                r = subprocess.run([self._cli, "auth", "status", "--platform", "toutiao"],
                                   capture_output=True, text=True, timeout=10)
                return r.returncode == 0 and "valid" in r.stdout.lower()
            except Exception:
                return False
        try:
            from super_publisher.platforms.toutiao import ToutiaoClient
            c = ToutiaoClient()
            return c.is_logged_in()
        except Exception:
            return False

    def publish(self, article: dict, options: dict = None) -> ProviderResult:
        """通过 super-publisher 发布到头条号。"""
        options = options or {}
        try:
            if self._cli:
                return self._publish_via_cli(article, options)
            return self._publish_via_api(article, options)
        except ProviderError:
            raise
        except Exception as e:
            return ProviderResult(False, "toutiao", error=str(e)[:300])

    def _publish_via_cli(self, article: dict, options: dict) -> ProviderResult:
        """通过 CLI 发布（推荐，进程隔离）。"""
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                         delete=False, encoding="utf-8") as f:
            json.dump({
                "title": article.get("title", ""),
                "content": article.get("content_md", ""),
                "tags": article.get("tags", ""),
                "category": (options.get("category") or "").strip() or None,
                "draft_only": options.get("draft_only", False),
            }, f, ensure_ascii=False)
            tmp_path = f.name

        try:
            r = subprocess.run(
                [self._cli, "publish", "--platform", "toutiao", "--file", tmp_path],
                capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                # super-publisher CLI 输出 JSON: {post_id, post_url, ...}
                try:
                    data = json.loads(r.stdout)
                    return ProviderResult(
                        True, "toutiao",
                        post_id=str(data.get("post_id", "")),
                        post_url=data.get("post_url", ""),
                        edit_url=data.get("edit_url", ""),
                        raw=data)
                except json.JSONDecodeError:
                    return ProviderResult(True, "toutiao",
                                         post_url=r.stdout.strip()[:200])
            return ProviderResult(False, "toutiao", error=r.stderr[:300])
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def _publish_via_api(self, article: dict, options: dict) -> ProviderResult:
        """通过 Python API 发布（同进程调用）。"""
        from super_publisher.platforms.toutiao import ToutiaoClient

        client = ToutiaoClient()
        result = client.publish(
            title=article.get("title", ""),
            content=article.get("content_md", ""),
            tags=article.get("tags", ""),
            category=(options.get("category") or "").strip() or None,
            draft_only=options.get("draft_only", False),
        )
        return ProviderResult(
            result.get("ok", False), "toutiao",
            post_id=str(result.get("post_id", "")),
            post_url=result.get("post_url", ""),
            raw=result)

    def update(self, post_id: str, article: dict, options: dict = None) -> ProviderResult:
        """更新头条号文章。"""
        options = options or {}
        try:
            from super_publisher.platforms.toutiao import ToutiaoClient
            client = ToutiaoClient()
            result = client.update(post_id, article.get("content_md", ""))
            return ProviderResult(True, "toutiao", post_id=post_id, raw=result)
        except Exception as e:
            return ProviderResult(False, "toutiao", post_id=post_id, error=str(e)[:300])
