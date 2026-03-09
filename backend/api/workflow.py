"""Workflow routes: run, stop, ws/logs."""

import json
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent import Agent
from events import emit_agent_event, emit_event, log_to_client, manager
from llm import OllamaInterface
from runtime import WorkflowRunner
from tools import (
    class_name_to_output_pattern,
    get_session_settings,
    initialize_workflow_session,
    set_workflow_run_id,
    set_workflow_session_id,
    write_session_code,
)
from workflow_state import cancel_requested

from agent_parser import extract_agent_configs

from .schemas import RunRequest

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
async def stop_workflow() -> dict[str, str]:
    cancel_requested.set()
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

    from tools import read_workflow_snapshot

    snapshot = read_workflow_snapshot(session_id)
    if snapshot is None:
        return {
            "status": "error",
            "message": "Session not found.",
        }

    _debug_log(
        "H1",
        "run_agent_start",
        {
            "codeLength": len(request.code),
            "sessionId": session_id,
        },
    )
    agent_configs = extract_agent_configs(request.code)
    if not agent_configs:
        await log_to_client(
            "Error: Failed to parse agent parameters from the submitted script."
        )
        return {
            "status": "error",
            "message": (
                "Could not extract any class-based Agent definitions "
                "(class X(Agent): ... variable = X(task=..., input=...))."
            ),
        }

    variable_to_name = {
        config["variable"]: config["name"] for config in agent_configs
    }
    variable_to_config = {
        config["variable"]: config for config in agent_configs
    }

    for config in agent_configs:
        input_source_variable = config.get("inputSourceVariable")

        if input_source_variable is None:
            continue

        if input_source_variable not in variable_to_config:
            await log_to_client(
                "An agent input referenced an undefined upstream agent output."
            )
            return {
                "status": "error",
                "message": (
                    f"Agent '{config['variable']}' references undefined "
                    f"input source '{input_source_variable}.output'."
                ),
            }

    max_rounds = request.maxRounds if request.maxRounds is not None else 8
    session_settings = get_session_settings(session_id)
    llm_interface = OllamaInterface(settings=session_settings)
    agents = [
        Agent(
            name=str(config["name"]),
            task=str(config["task"]),
            role=str(config.get("role") or ""),
            output_file=class_name_to_output_pattern(config["className"]),
            input_source=(
                variable_to_name.get(str(config["inputSourceVariable"]))
                if config.get("inputSourceVariable") is not None
                else None
            ),
            llm=llm_interface,
            tools=config.get("tools"),
        )
        for config in agent_configs
    ]
    connections: dict[str, str] = {}

    for config in agent_configs:
        input_source_variable = config.get("inputSourceVariable")

        if input_source_variable is None:
            continue

        source_agent_name = variable_to_name.get(str(input_source_variable))
        target_agent_name = str(config["name"])
        if source_agent_name is None:
            continue

        if source_agent_name in connections:
            await log_to_client(
                "Multiple agents cannot consume the same output in this MVP."
            )
            return {
                "status": "error",
                "message": (
                    f"Output from '{source_agent_name}' is connected to "
                    "multiple agents. This MVP supports a single "
                    "downstream per output."
                ),
            }

        connections[source_agent_name] = target_agent_name

    start_agent_name = (
        next(
            (
                config["name"]
                for config in agent_configs
                if config.get("inputSourceVariable") is None
            ),
            None,
        )
        or agent_configs[0]["name"]
    )

    agent_order = [config["name"] for config in agent_configs]
    runner = WorkflowRunner(
        agents=agents,
        start_agent_name=start_agent_name,
        max_rounds=max_rounds,
        connections=connections,
    )
    _debug_log(
        "H1",
        "run_agent_parsed",
        {
            "agentCount": len(agents),
            "startAgentName": start_agent_name,
            "connections": connections,
        },
    )
    run_id = uuid.uuid4().hex[:6]
    set_workflow_session_id(session_id)
    set_workflow_run_id(run_id)
    agent_output_files = {
        c["name"]: class_name_to_output_pattern(c["className"])
        for c in agent_configs
    }
    initialize_workflow_session(session_id, agent_order, run_id=run_id, agent_output_files=agent_output_files)
    write_session_code(request.code, session_id)

    for agent in agents:
        agent.add_to_memory("Agent instantiated from submitted script.")
        await emit_agent_event(
            agent_name=agent.name,
            event_type="state",
            message=f"Instantiated agent '{agent.name}' with task '{agent.task}'.",
            state="waiting_for_turn",
            round_number=0,
        )

    await emit_event(
        event_type="workflow_started",
        message=f"Workflow {session_id}-{run_id} started.",
        state="running",
        agent_order=agent_order,
        session_id=session_id,
        run_id=run_id,
    )
    try:
        await runner.run()
        return {
            "status": "ok",
            "message": f"Workflow finished for {len(agents)} agent(s).",
            "sessionId": session_id,
            "runId": run_id,
        }
    finally:
        set_workflow_session_id(None)
        set_workflow_run_id(None)


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
