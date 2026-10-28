from app.routes.admin import create_admin_router
from app.routes.debug import create_debug_router
from app.routes.demo import create_demo_router

__all__ = ["create_admin_router", "create_debug_router", "create_demo_router"]
