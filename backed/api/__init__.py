"""API 路由包：聚合各版本路由并挂载到应用。

注：`register_hub`（挂 `/api/v1/hub`）在 `api/hub.py` 里，才是实际入口。
本模块只保留 `hub_router` 导出（供 `app/routes.py` 列举路由信息）。
旧版 `register_routers`（挂 `/api/hub`、未版本化）已因与 `register_hub` 不一致
而删掉，避免使用者以为 prefix 可配置但实际写死 `/api/v1/hub`。
"""

from fastapi import FastAPI  # noqa: F401  (re-exported for API compat)

from .hub import hub_router  # noqa: F401  (exported)

__all__ = ["hub_router", "get_router_info"]


def get_router_info() -> dict:
    """当前 API 路由概览（调试接口 /api/info 用）。"""
    routes = []
    for route in hub_router.routes:
        routes.append(
            {
                "path": getattr(route, "path", ""),
                "methods": sorted(getattr(route, "methods", None) or []),
                "name": getattr(route, "name", ""),
            }
        )
    return {
        "prefix": "/api/v1/hub",  # 与 register_hub 保持一致
        "routes": routes,
    }
