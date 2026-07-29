"""Multi-clinic administration API routers."""

from fastapi import APIRouter

from app.api.admin import (
    accounts,
    activity,
    content,
    core,
    enterprise,
    overview,
    realtime_preview,
    test_console,
)

router = APIRouter()
router.include_router(accounts.router)
router.include_router(core.router)
router.include_router(content.router)
router.include_router(activity.router)
router.include_router(enterprise.router)
router.include_router(test_console.router)
router.include_router(overview.router)
router.include_router(realtime_preview.router)
