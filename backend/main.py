from datetime import datetime, UTC
import json
from pathlib import Path
import re
import time
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from llm import list_available_ollama_models
from runtime import Agent, Workflow, WorkflowRunner
from storage import load_settings, save_settings
from tools import (
    get_workflow_session_id,
    initialize_workflow_session,
    read_session_result_file,
    read_workflow_snapshot,
    record_agent_output,
    set_workflow_session_id,
    sync_workflow_event,
)
from workflow_state import cancel_requested


DEBUG_LOG_PATH = Path(__file__).resolve().parents[1] / "debug-ecf5ab.log"


def _debug_log(hypothesis_id: str, message: str, data: dict[str, object]) -> None:
    payload = {
        "sessionId": "ecf5ab",
        "runId": "pre-fix",
        "hypothesisId": hypothesis_id,
        "location": "backend/main.py",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with DEBUG_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(payload) + "\n")


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=
    [
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=
    [
        "*",
    ],
    allow_headers=
    [
        "*",
    ],
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
            except RuntimeError:
                disconnected_connections.append(connection)

        for connection in disconnected_connections:
            self.disconnect(connection)


manager = ConnectionManager()


class RunRequest(BaseModel):
    code: str


class SettingsUpdateRequest(BaseModel):
    model: str
    timeout: float
    llm_server: str


def _normalize_llm_server(raw: str) -> str:
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    return url.rstrip("/")


async def log_to_client(message: str) -> None:
    await emit_event(event_type="system", message=message)


async def emit_event(
    event_type: str,
    message: str,
    level: str = "info",
    state: str | None = None,
    agent_name: str | None = None,
    round_number: int | None = None,
    agent_order: list[str] | None = None,
    session_id: str | None = None,
) -> None:
    resolved_session_id = session_id or get_workflow_session_id()
    payload = (
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "eventType": event_type,
            "message": message,
        }
    )

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
    payload: dict[str, Any] = (
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": "info",
            "eventType": "agent_output",
            "agentName": agent_name,
            "output": output,
        }
    )
    if session_id is not None:
        payload["sessionId"] = session_id

    record_agent_output(agent_name=agent_name, output=output, session_id=session_id)
    await manager.broadcast(payload)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
    }


@app.get("/settings")
async def get_settings() -> dict[str, Any]:
    settings = load_settings()
    llm_server = _normalize_llm_server(str(settings.get("llm_server", "http://localhost:11434")))

    try:
        available_models = await list_available_ollama_models(llm_server)
    except Exception:
        available_models = []

    current_model = str(settings.get("model", "qwen3:4b"))
    if current_model not in available_models:
        available_models.insert(0, current_model)

    return {
        "provider": str(settings.get("provider", "ollama")),
        "model": current_model,
        "timeout": float(settings.get("timeout", 240.0)),
        "llm_server": llm_server,
        "availableModels": available_models,
    }


@app.get("/sessions/{session_id}/workflow")
async def get_workflow_session(session_id: str) -> dict[str, Any]:
    snapshot = read_workflow_snapshot(session_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    return snapshot


@app.get("/sessions/{session_id}/results/{filename:path}")
async def get_session_result_file(session_id: str, filename: str) -> dict[str, str]:
    try:
        content = read_session_result_file(session_id, filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Result file not found.") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session or filename.") from None

    return {
        "filename": Path(filename).name,
        "content": content,
    }


@app.put("/settings")
async def update_settings(request: SettingsUpdateRequest) -> dict[str, Any]:
    model = request.model.strip()
    timeout = float(request.timeout)
    llm_server = request.llm_server.strip()

    if model == "":
        return {
            "status": "error",
            "message": "Model cannot be empty.",
        }

    if timeout <= 0:
        return {
            "status": "error",
            "message": "Timeout must be greater than zero.",
        }

    if llm_server == "":
        return {
            "status": "error",
            "message": "LLM server cannot be empty.",
        }

    updated_settings = save_settings(
        {
            "provider": "ollama",
            "model": model,
            "timeout": timeout,
            "llm_server": _normalize_llm_server(llm_server),
        }
    )

    return {
        "status": "ok",
        "settings": updated_settings,
    }


def extract_string_argument(arguments: str, argument_name: str) -> str | None:
    match = re.search(
        rf'{argument_name}\s*=\s*(?P<quote>["\'])(?P<value>.*?)(?P=quote)',
        arguments,
        re.DOTALL,
    )
    if match is None:
        return None

    return match.group("value")


def extract_input_source_variable(arguments: str) -> str | None:
    match = re.search(
        r'input\s*=\s*(?P<source_variable>\w+)\.output',
        arguments,
    )
    if match is None:
        return None

    return match.group("source_variable")


def extract_agent_configs(code: str) -> list[dict[str, str | None]]:
    matches = re.finditer(
        r'(?P<variable>\w+)\s*=\s*Agent\((?P<arguments>.*?)\)',
        code,
        re.DOTALL,
    )
    agent_configs: list[dict[str, str | None]] = []

    for match in matches:
        arguments = match.group("arguments")
        name = extract_string_argument(arguments, "name")
        goal = extract_string_argument(arguments, "goal")

        if name is None or goal is None:
            continue

        agent_configs.append(
            {
                "variable": match.group("variable"),
                "name": name,
                "goal": goal,
                "role": extract_string_argument(arguments, "role"),
                "inputSourceVariable": extract_input_source_variable(arguments),
            }
        )

    return agent_configs


def extract_start_agent_variable(code: str) -> str | None:
    match = re.search(r'(?P<variable>\w+)\.loop\(', code)
    if match is None:
        return None

    return match.group("variable")


def extract_workflow_config(code: str) -> dict[str, Any] | None:
    match = re.search(
        r'(?P<variable>\w+)\s*=\s*Workflow\(\s*agents\s*=\s*\[(?P<agents>.*?)\]\s*,\s*start_agent\s*=\s*["\'](?P<start_agent>[^"\']+)["\']\s*,\s*max_rounds\s*=\s*(?P<max_rounds>\d+)\s*,?\s*\)',
        code,
        re.DOTALL,
    )
    if match is None:
        return None

    workflow_variable = match.group("variable")
    run_call_match = re.search(rf'{workflow_variable}\.run\(\s*\)', code)
    if run_call_match is None:
        return None

    agent_variables = re.findall(r'["\']([^"\']+)["\']', match.group("agents"))
    return {
        "agentVariables": agent_variables,
        "entryAgent": match.group("start_agent"),
        "maxRounds": int(match.group("max_rounds")),
    }


@app.post("/stop")
async def stop_workflow() -> dict[str, str]:
    cancel_requested.set()
    return {
        "status": "ok",
        "message": "Stop requested.",
    }


@app.post("/run")
async def run_agent(request: RunRequest) -> dict[str, Any]:
    cancel_requested.clear()
    # region agent log
    _debug_log(
        "H1",
        "run_agent_start",
        {
            "codeLength": len(request.code),
            "hasWorkflowRun": "workflow.run()" in request.code,
            "hasAgentOutputReference": ".output" in request.code,
        },
    )
    # endregion
    agent_configs = extract_agent_configs(request.code)
    if not agent_configs:
        await log_to_client("Error: Failed to parse agent parameters from the submitted script.")
        return {
            "status": "error",
            "message": "Could not extract any Agent(name=..., goal=...) definitions from the script.",
        }

    workflow_config = extract_workflow_config(request.code)
    if workflow_config is None:
        await log_to_client("Error: Failed to parse workflow configuration from the submitted script.")
        return {
            "status": "error",
            "message": "Could not extract Workflow(agents=[...], start_agent=..., max_rounds=...) plus workflow.run() from the script.",
        }

    variable_to_name = (
        {
            config["variable"]: config["name"]
            for config in agent_configs
        }
    )
    variable_to_config = (
        {
            config["variable"]: config
            for config in agent_configs
        }
    )

    selected_agent_configs = (
        [
            variable_to_config[agent_variable]
            for agent_variable in workflow_config["agentVariables"]
            if agent_variable in variable_to_config
        ]
    )
    if not selected_agent_configs:
        await log_to_client("Workflow did not reference any valid agent variables.")
        return {
            "status": "error",
            "message": "The workflow must reference one or more defined agent variables.",
        }

    for config in selected_agent_configs:
        input_source_variable = config.get("inputSourceVariable")

        if input_source_variable is None:
            continue

        if input_source_variable not in variable_to_config:
            await log_to_client("An agent input referenced an undefined upstream agent output.")
            return {
                "status": "error",
                "message": f"Agent '{config['variable']}' references undefined input source '{input_source_variable}.output'.",
            }

    workflow = Workflow(
        agents=workflow_config["agentVariables"],
        start_agent=workflow_config["entryAgent"],
        max_rounds=workflow_config["maxRounds"],
    )
    agents = (
        [
            Agent(
                name=str(config["name"]),
                goal=str(config["goal"]),
                role=str(config.get("role") or ""),
                input_source=(
                    variable_to_name.get(str(config["inputSourceVariable"]))
                    if config.get("inputSourceVariable") is not None
                    else None
                ),
            )
            for config in selected_agent_configs
        ]
    )
    connections: dict[str, str] = {}

    for config in selected_agent_configs:
        input_source_variable = config.get("inputSourceVariable")

        if input_source_variable is None:
            continue

        source_agent_name = variable_to_name.get(str(input_source_variable))
        target_agent_name = str(config["name"])
        if source_agent_name is None:
            continue

        if source_agent_name in connections:
            await log_to_client("Multiple agents cannot consume the same output in this MVP.")
            return {
                "status": "error",
                "message": f"Output from '{source_agent_name}' is connected to multiple agents. This MVP supports a single downstream per output.",
            }

        connections[source_agent_name] = target_agent_name

    start_agent_name = variable_to_name.get(workflow.start_agent) if workflow.start_agent else agents[0].name

    agent_order = [config["name"] for config in selected_agent_configs]
    runner = WorkflowRunner(
        agents=agents,
        start_agent_name=start_agent_name,
        max_rounds=workflow.max_rounds,
        connections=connections,
    )
    # region agent log
    _debug_log(
        "H1",
        "run_agent_parsed",
        {
            "agentCount": len(agents),
            "startAgentName": start_agent_name,
            "connections": connections,
        },
    )
    # endregion
    import uuid

    session_id = uuid.uuid4().hex[:6]
    set_workflow_session_id(session_id)
    initialize_workflow_session(session_id, agent_order)

    for agent in agents:
        agent.add_to_memory("Agent instantiated from submitted script.")
        await emit_agent_event(
            agent_name=agent.name,
            event_type="state",
            message=f"Instantiated agent '{agent.name}' with goal '{agent.goal}'.",
            state="waiting_for_turn",
            round_number=0,
        )

    await emit_event(
        event_type="workflow_started",
        message="Workflow started.",
        state="running",
        agent_order=agent_order,
        session_id=session_id,
    )
    try:
        await runner.run()
        return {
            "status": "ok",
            "message": f"Workflow finished for {len(agents)} agent(s).",
            "sessionId": session_id,
        }
    finally:
        set_workflow_session_id(None)


@app.websocket("/ws/logs")
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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
