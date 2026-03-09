"""Workflow routes: run, stop, ws/logs."""

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, WebSocket, WebSocketDisconnect

from events import emit_event, manager
from workflow_state import request_cancel

from services import run_workflow

from .schemas import RunRequest, StopRequest

router = APIRouter()

DEBUG_LOG_PATH = Path(__file__).resolve().parents[2] / "debug-ecf5ab.log"


def _debug_log(hypothesis_id: str, message: str, data: dict[str, object]) -> None:
    payload = {
        "sessionId": "ecf5ab",
        "runId": "pre-fix",
        "hypothesisId": hypothesis_id,
        "location": "backend/api/workflow.py",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with DEBUG_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(payload) + "\n")


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

    _debug_log(
        "H1",
        "run_agent_start",
        {
            "codeLength": len(request.code),
            "sessionId": session_id,
        },
    )

    max_rounds = request.maxRounds if request.maxRounds is not None else 8
    result = await run_workflow(
        session_id=session_id,
        code=request.code,
        max_rounds=max_rounds,
    )

    if result.get("status") == "ok":
        _debug_log(
            "H1",
            "run_agent_success",
            {
                "sessionId": result.get("sessionId"),
                "runId": result.get("runId"),
            },
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
