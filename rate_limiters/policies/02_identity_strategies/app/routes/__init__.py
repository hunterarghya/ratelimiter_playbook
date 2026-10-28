"""Routes package for identity strategies."""

from app.routes.debug import create_debug_router
from app.routes.demo import create_demo_router

__all__ = ["create_demo_router", "create_debug_router"]
