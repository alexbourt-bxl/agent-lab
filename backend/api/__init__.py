"""API package: registers all routers."""

from fastapi import APIRouter

from . import agents, sessions, workflow

router = APIRouter()
router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
router.include_router(agents.router, prefix="/agents", tags=["agents"])
router.include_router(workflow.router, tags=["workflow"])
