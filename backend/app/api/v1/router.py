"""API v1 router."""

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.mcp import router as mcp_router
from app.api.v1.stash import router as stash_router
from app.api.v1.users import router as users_router
from app.api.v1.workspaces import router as workspaces_router
from app.api.v1.websocket import router as websocket_router

router = APIRouter(prefix="/api/v1")

# Include routers
router.include_router(admin_router)
router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(feedback_router)
router.include_router(stash_router)
router.include_router(users_router)
router.include_router(workspaces_router)
router.include_router(mcp_router)
router.include_router(websocket_router)


@router.get("/status")
async def status():
    """API status endpoint."""
    return {"status": "ok", "version": "v1"}

