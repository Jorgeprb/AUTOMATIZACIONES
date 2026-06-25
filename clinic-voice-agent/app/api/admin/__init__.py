"""Multi-clinic administration API routers."""

from fastapi import APIRouter

from app.api.admin import activity, content, core, overview, test_console

router = APIRouter()
router.include_router(core.router)
router.include_router(content.router)
router.include_router(activity.router)
router.include_router(test_console.router)
router.include_router(overview.router)
