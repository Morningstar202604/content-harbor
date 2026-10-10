# -*- coding: utf-8 -*-
"""B 站视频投稿：基于 biliup-rs / biliup 的外部工具封装。

biliup 是 B 站投稿领域最成熟的开源工具：
  - Python 原版：github.com/biliup/biliup（仍维护）
  - Rust 重写版：github.com/biliup/biliup-rs（活跃，更高性能）

支持功能：视频投稿、分P上传、弹幕录制、直播回放、Cookie/短信/扫码登录。

安装方式（待接入时执行）：
  pip install biliup                           # Python 版
  cargo install biliup-rs                      # Rust 版（推荐性能场景）

注意：bilibili-api (Nemo2011) 已被 DMCA 下架，不可用。
"""

import json
import shutil
import subprocess
from pathlib import Path

from .base import PublishProvider, ProviderResult
from .registry import register


@register("bilibili")
class BilibiliProvider(PublishProvider):
    """B 站视频投稿 provider：复用 biliup 生态。"""

    tool_name = "biliup-rs"
    tool_url = "https://github.com/biliup/biliup-rs"

    def __init__(self):
        self._cli = None
        self._mode = None  # "rs" (biliup-rs) 或 "py" (biliup)

    def is_available(self) -> bool:
        for cmd, mode in (("biliup-rs", "rs"), ("biliup", "py")):
            path = shutil.which(cmd)
            if path:
                self._cli = path
                self._mode = mode
                return True
        try:
            import biliup  # noqa: F401
            self._mode = "py"
            return True
        except ImportError:
            pass
        return False

    def check_auth(self) -> bool:
        if not self.is_available():
            return False
        if self._cli:
            try:
                r = subprocess.run([self._cli, "auth", "check"],
                                   capture_output=True, text=True, timeout=15)
                return r.returncode == 0 and ("valid" in r.stdout.lower()
                                               or "有效" in r.stdout)
            except Exception:
                return False
        try:
            from biliup.app import check_login
            return check_login()
        except Exception:
            return False

    def publish(self, article: dict, options: dict = None) -> ProviderResult:
        """投稿视频到 B 站。

        article 需要包含 video_path（视频文件路径）。
        """
        options = options or {}
        video_path = article.get("video_path") or options.get("video_path", "")
        if not video_path or not Path(video_path).exists():
            return ProviderResult(False, "bilibili",
                                 error=f"video_path 无效: {video_path}")

        try:
            if self._cli:
                return self._publish_via_cli(article, options, video_path)
            return self._publish_via_api(article, options, video_path)
        except Exception as e:
            return ProviderResult(False, "bilibili", error=str(e)[:300])

    def _publish_via_cli(self, article, options, video_path):
        cmd = [self._cli, "upload", video_path,
               "--title", article.get("title", ""),
               "--desc", article.get("summary") or article.get("content_md", "")[:500],
               "--tag", article.get("tags", ""),
               "--category", options.get("category", "")]
        if options.get("draft_only"):
            cmd.append("--draft")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode == 0:
            return ProviderResult(True, "bilibili", post_url=r.stdout.strip()[:200])
        return ProviderResult(False, "bilibili", error=r.stderr[:300])

    def _publish_via_api(self, article, options, video_path):
        from biliup.uploader import upload_video
        r = upload_video(
            video_path=video_path,
            title=article.get("title", ""),
            desc=article.get("summary") or article.get("content_md", "")[:500],
            tags=article.get("tags", "").split(","),
        )
        return ProviderResult(r.get("ok", False), "bilibili",
                              post_url=r.get("url", ""), raw=r)

    def update(self, post_id: str, article: dict, options: dict = None) -> ProviderResult:
        return ProviderResult(False, "bilibili", post_id=post_id,
                             error="biliup 不支持原地更新，需手动到创作中心修改")

    def list_articles(self, limit: int = 50) -> list:
        if not self.is_available():
            return []
        try:
            if self._cli:
                r = subprocess.run([self._cli, "video", "list", "--limit", str(limit)],
                                   capture_output=True, text=True, timeout=15)
                if r.returncode == 0:
                    return json.loads(r.stdout)
            from biliup.app import list_videos
            return list_videos(limit=limit)
        except Exception:
            return []
