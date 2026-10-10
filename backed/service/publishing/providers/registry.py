# -*- coding: utf-8 -*-
"""Provider 注册表：解析平台 → 对应外部工具。"""

from .base import PublishProvider

# provider 注册表（platform_id → class）
_REGISTRY: dict[str, type[PublishProvider]] = {}


def register(platform_id: str):
    """类装饰器：自动注册 provider。"""
    def decorator(cls):
        cls.platform_id = platform_id
        _REGISTRY[platform_id] = cls
        return cls
    return decorator


def resolve_provider(platform_id: str) -> PublishProvider | None:
    """实例化指定平台的 provider（如果已注册）。"""
    cls = _REGISTRY.get(platform_id)
    return cls() if cls else None


def list_available_providers() -> list[dict]:
    """列出所有可用的 provider（工具已安装 + 已登录）。"""
    result = []
    for pid, cls in _REGISTRY.items():
        try:
            inst = cls()
            result.append({
                "platform_id": pid,
                "tool_name": inst.tool_name,
                "tool_url": inst.tool_url,
                "available": inst.is_available(),
                "authed": inst.check_auth() if inst.is_available() else False,
            })
        except Exception:
            pass
    return result


def all_providers() -> dict[str, type[PublishProvider]]:
    """返回全部已注册的 provider 类。"""
    return dict(_REGISTRY)
