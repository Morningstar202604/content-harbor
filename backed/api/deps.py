# -*- coding: utf-8 -*-
"""子路由器共享依赖：get_hub() / get_task_manager() / 鉴权检查。"""

_hub_instance = None


def get_hub():
    """惰性创建 Hub 实例，避免模块导入时产生副作用。"""
    global _hub_instance
    if _hub_instance is None:
        from service.publishing.service import Hub
        _hub_instance = Hub(headless=True)
    return _hub_instance


def get_task_manager():
    """返回 Hub 内部的 TaskManager。

    .. deprecated:: 统一通过 ``get_hub().tasks`` 访问。
    """
    return get_hub().tasks
