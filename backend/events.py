"""WebSocket connection manager and event emission."""

from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from tools import (
    get_workflow_run_id,
    get_workflow_session_id,
    record_agent_output,
    sync_workflow_event,
)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        disconnected_connections: list[WebSocket] = []

        for connection in self.active_connections:
            try:
                await connection.send_json(payload)
            except (RuntimeError, WebSocketDisconnect, OSError):
                disconnected_connections.append(connection)

        for connection in disconnected_connections:
            self.disconnect(connection)


manager = ConnectionManager()


async def emit_event(
    event_type: str,
    message: str,
    level: str = "info",
    state: str | None = None,
    agent_name: str | None = None,
    round_number: int | None = None,
    agent_order: list[str] | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
) -> None:
    resolved_session_id = session_id or get_workflow_session_id()
    resolved_run_id = run_id or get_workflow_run_id()
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": level,
        "eventType": event_type,
        "message": message,
    }

    if state is not None:
        payload["state"] = state

    if agent_name is not None:
        payload["agentName"] = agent_name

    if round_number is not None:
        payload["round"] = round_number

    if agent_order is not None:
        payload["agentOrder"] = agent_order

    if resolved_session_id is not None:
        payload["sessionId"] = resolved_session_id

    if resolved_run_id is not None:
        payload["runId"] = resolved_run_id

    if event_type != "thought":
        sync_workflow_event(
            event_type=event_type,
            message=message,
            state=state,
            agent_name=agent_name,
            round_number=round_number,
            agent_order=agent_order,
            session_id=resolved_session_id,
        )

    await manager.broadcast(payload)


async def emit_agent_event(
    agent_name: str,
    event_type: str,
    message: str,
    state: str,
    round_number: int,
) -> None:
    await emit_event(
        event_type=event_type,
        message=message,
        state=state,
        agent_name=agent_name,
        round_number=round_number,
    )


async def emit_agent_output(agent_name: str, output: str) -> None:
    session_id = get_workflow_session_id()
    run_id = get_workflow_run_id()
    payload: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": "info",
        "eventType": "agent_output",
        "agentName": agent_name,
        "output": output,
    }
    if session_id is not None:
        payload["sessionId"] = session_id
    if run_id is not None:
        payload["runId"] = run_id

    record_agent_output(agent_name=agent_name, session_id=session_id)
    await manager.broadcast(payload)


async def log_to_client(message: str) -> None:
    await emit_event(event_type="system", message=message)
