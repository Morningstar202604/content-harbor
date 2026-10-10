# -*- coding: utf-8 -*-
"""外部成熟工具封装层：用开源社区验证过的方案做兜底，不重复造轮子。

每个 provider 是一层薄壳，负责：
  1. 检测外部工具是否已安装（二进制 / Node / Python 包）
  2. 把内容港的文章格式翻译成外部工具期望的输入
  3. 调用外部工具并解析输出
  4. 失败时返回标准错误，让 adapter 决定是否回退到 Playwright

对接方案来源（调研 2026-10）：
  - 头条号 / 多平台   -> super-publisher (Python + Playwright, ClawHub)
  - B 站视频投稿      -> biliup-rs (Rust CLI) 或 biliup (Python)
  - 微信公众号        -> wenyan-cli (Node.js, npm)
  - 知乎              -> ZhihuPublisher + zhihu-mediacloud-uploader (Python, GitHub @zhihu)
"""

from .base import PublishProvider, ProviderError, ProviderResult
from .registry import register, resolve_provider, list_available_providers, all_providers

# 导入触发注册（每个 provider 文件用 @register）
from . import toutiao      # noqa: F401
from . import bilibili     # noqa: F401

__all__ = [
    "PublishProvider", "ProviderError", "ProviderResult",
    "register", "resolve_provider", "list_available_providers", "all_providers",
]
