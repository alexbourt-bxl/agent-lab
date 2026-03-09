"""Workflow routes: run, stop, ws/logs."""

from typing import Any

from fastapi import APIRouter, Body, WebSocket, WebSocketDisconnect

from events import emit_event, manager
from workflow_state import cancel_requested, request_cancel

from services import run_workflow

from .schemas import RunRequest, StopRequest

router = APIRouter()


@router.post("/stop")
async def stop_workflow(body: StopRequest | None = Body(default=None)) -> dict[str, str]:
    session_id = (
        ((body.sessionId or "").strip()[:6] or None)
        if body is not None
        else None
    )
    request_cancel(session_id)
    return {
        "status": "ok",
        "message": "Stop requested.",
    }


@router.post("/run")
async def run_agent(request: RunRequest) -> dict[str, Any]:
    cancel_requested.clear()
    session_id = (request.sessionId or "").strip()[:6]
    if not session_id:
        return {
            "status": "error",
            "message": "Session ID is required.",
        }

    result = await run_workflow(
        session_id=session_id,
        code=request.code,
    )

    return result


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    await emit_event(
        event_type="system",
        message="Connected to execution logs.",
        state="connected",
    )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
