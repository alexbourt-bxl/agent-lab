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

from llm import OllamaInterface, list_available_ollama_models
from agent import Agent
from runtime import WorkflowRunner
from tools import (
    class_name_to_output_pattern,
    create_session,
    delete_session_file,
    get_session_settings,
    list_session_files,
    get_workflow_run_id,
    get_workflow_session_id,
    initialize_workflow_session,
    read_session_result_file,
    read_workflow_snapshot,
    record_agent_output,
    set_workflow_run_id,
    set_workflow_session_id,
    sync_workflow_event,
    update_session_settings,
    write_session_code,
    write_session_file,
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
    sessionId: str
    maxRounds: int | None = 8


class SessionFileUpdateRequest(BaseModel):
    content: str


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
    run_id: str | None = None,
) -> None:
    resolved_session_id = session_id or get_workflow_session_id()
    resolved_run_id = run_id or get_workflow_run_id()
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

    if resolved_run_id is not None:
        payload["runId"] = resolved_run_id

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
    if run_id is not None:
        payload["runId"] = run_id

    record_agent_output(agent_name=agent_name, session_id=session_id)
    await manager.broadcast(payload)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
    }


@app.post("/sessions/create")
def create_session_endpoint() -> dict[str, str]:
    session_id = create_session()
    return {"sessionId": session_id}


@app.get("/sessions/{session_id}/settings")
async def get_session_settings_endpoint(session_id: str) -> dict[str, Any]:
    snapshot = read_workflow_snapshot(session_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    settings = get_session_settings(session_id)
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


@app.get("/sessions/{session_id}/files")
async def get_session_files(session_id: str) -> dict[str, list[str]]:
    try:
        files = list_session_files(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session.") from None

    return {"files": files}


@app.get("/sessions/{session_id}/workflow")
async def get_workflow_session(session_id: str) -> dict[str, Any]:
    snapshot = read_workflow_snapshot(session_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    return snapshot


@app.get("/sessions/{session_id}/{filename:path}")
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


@app.put("/sessions/{session_id}/{filename:path}")
async def put_session_file(
    session_id: str,
    filename: str,
    request: SessionFileUpdateRequest,
) -> dict[str, str]:
    try:
        write_session_file(session_id, filename, request.content)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session or filename.") from None

    return {"status": "ok"}


@app.delete("/sessions/{session_id}/{filename:path}")
async def delete_session_file_endpoint(session_id: str, filename: str) -> dict[str, str]:
    try:
        delete_session_file(session_id, filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session or filename.") from None

    return {"status": "ok"}


@app.put("/sessions/{session_id}/settings")
async def update_session_settings_endpoint(session_id: str, request: SettingsUpdateRequest) -> dict[str, Any]:
    snapshot = read_workflow_snapshot(session_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Session not found.")

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

    update_session_settings(
        {
            "provider": "ollama",
            "model": model,
            "timeout": timeout,
            "llm_server": _normalize_llm_server(llm_server),
        },
        session_id=session_id,
    )

    updated_settings = get_session_settings(session_id)
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


def _extract_class_attrs(
    code: str,
    start: int,
    end: int,
) -> dict[str, Any]:
    from tools import TOOL_REGISTRY

    body = code[start:end]
    attrs: dict[str, Any] = {}
    name_match = re.search(r'name\s*=\s*["\']([^"\']*)["\']', body)
    role_match = re.search(r'role\s*=\s*["\']([^"\']*)["\']', body)
    tools_match = re.search(r"tools\s*=\s*\[([^\]]+)\]", body)
    if name_match:
        attrs["name"] = name_match.group(1)
    if role_match:
        attrs["role"] = role_match.group(1)
    if tools_match:
        tool_names = [
            t.strip() for t in tools_match.group(1).split(",")
        ]
        attrs["tools"] = [
            TOOL_REGISTRY[t]
            for t in tool_names
            if t in TOOL_REGISTRY
        ]
    return attrs


def extract_agent_configs(code: str) -> list[dict[str, Any]]:
    from tools import ReadFile, WriteFile

    class_matches = list(re.finditer(r"class (\w+)\(Agent\):\s*", code))
    classes_by_name: dict[str, dict[str, Any]] = {}

    for i, match in enumerate(class_matches):
        class_name = match.group(1)
        body_start = match.end()
        body_end = (
            class_matches[i + 1].start()
            if i + 1 < len(class_matches)
            else len(code)
        )
        next_class = re.search(r"\nclass \w+\(Agent\)", code[body_start:])
        if next_class:
            body_end = body_start + next_class.start()
        attrs = _extract_class_attrs(code, body_start, body_end)
        classes_by_name[class_name] = {
            "name": attrs.get("name", class_name),
            "role": attrs.get("role", ""),
            "tools": attrs.get("tools", [ReadFile, WriteFile]),
        }

    configs: list[dict[str, Any]] = []
    for class_name in classes_by_name:
        pattern = rf"(\w+)\s*=\s*{re.escape(class_name)}\s*\(\s*([^)]*)\)"
        for m in re.finditer(pattern, code):
            variable = m.group(1)
            arguments = m.group(2)
            task = extract_string_argument(arguments, "task") or extract_string_argument(
                arguments, "goal"
            )
            if not task:
                continue
            configs.append(
                {
                    "variable": variable,
                    "className": class_name,
                    "name": (
                        str(classes_by_name[class_name]["name"]).strip()
                        or class_name
                    ),
                    "role": str(classes_by_name[class_name]["role"] or ""),
                    "task": task,
                    "inputSourceVariable": extract_input_source_variable(
                        arguments
                    ),
                    "tools": classes_by_name[class_name]["tools"],
                }
            )
            break

    def order_key(c: dict[str, Any]) -> int:
        return code.index(f'{c["variable"]} = {c["className"]}')

    configs.sort(key=order_key)
    return configs


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
    session_id = (request.sessionId or "").strip()[:6]
    if not session_id:
        return {
            "status": "error",
            "message": "Session ID is required.",
        }

    snapshot = read_workflow_snapshot(session_id)
    if snapshot is None:
        return {
            "status": "error",
            "message": "Session not found.",
        }

    # region agent log
    _debug_log(
        "H1",
        "run_agent_start",
        {
            "codeLength": len(request.code),
            "sessionId": session_id,
        },
    )
    # endregion
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
