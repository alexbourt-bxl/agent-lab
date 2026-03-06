from datetime import datetime, UTC
import re
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from runtime import Agent, WorkflowRunner
from storage import AGENTS_DIR, SCRIPTS_DIR, load_record, load_records, save_record


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


class ScriptSaveRequest(BaseModel):
    id: str | None = None
    name: str
    code: str


class AgentSaveRequest(BaseModel):
    code: str
    source_script_id: str | None = None


async def log_to_client(message: str) -> None:
    await emit_event(event_type="system", message=message)


async def emit_event(
    event_type: str,
    message: str,
    level: str = "info",
    state: str | None = None,
    agent_name: str | None = None,
    round_number: int | None = None,
) -> None:
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


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
    }


def extract_agent_configs(code: str) -> list[dict[str, str]]:
    matches = re.finditer(
        r'(?P<variable>\w+)\s*=\s*Agent\(\s*name\s*=\s*["\'](?P<name>[^"\']+)["\']\s*,\s*goal\s*=\s*["\'](?P<goal>[^"\']+)["\']\s*\)',
        code,
    )
    return [
        {
            "variable": match.group("variable"),
            "name": match.group("name"),
            "goal": match.group("goal"),
        }
        for match in matches
    ]


def extract_entry_agent_variable(code: str) -> str | None:
    match = re.search(r'(?P<variable>\w+)\.loop\(', code)
    if match is None:
        return None

    return match.group("variable")


def build_script_record(
    record_id: str,
    name: str,
    code: str,
    agent_configs: list[dict[str, str]],
    entry_agent_variable: str | None,
) -> dict[str, Any]:
    return (
        {
            "id": record_id,
            "name": name,
            "code": code,
            "agents": agent_configs,
            "entryAgentVariable": entry_agent_variable,
            "updatedAt": datetime.now(UTC).isoformat(),
        }
    )


def save_agent_records(
    agent_configs: list[dict[str, str]],
    source_script_id: str | None,
) -> list[dict[str, Any]]:
    saved_records: list[dict[str, Any]] = []

    for agent_config in agent_configs:
        record_id = (
            f"{source_script_id}-{agent_config['variable']}"
            if source_script_id is not None
            else str(uuid4())
        )
        record = (
            {
                "id": record_id,
                "variable": agent_config["variable"],
                "name": agent_config["name"],
                "goal": agent_config["goal"],
                "sourceScriptId": source_script_id,
                "updatedAt": datetime.now(UTC).isoformat(),
            }
        )
        save_record(AGENTS_DIR, record_id, record)
        saved_records.append(record)

    return saved_records


@app.get("/scripts")
def list_scripts() -> list[dict[str, Any]]:
    return load_records(SCRIPTS_DIR)


@app.get("/scripts/{script_id}")
def get_script(script_id: str) -> dict[str, Any]:
    record = load_record(SCRIPTS_DIR, script_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Script not found.")

    return record


@app.post("/scripts")
def save_script(request: ScriptSaveRequest) -> dict[str, Any]:
    agent_configs = extract_agent_configs(request.code)
    if not agent_configs:
        raise HTTPException(
            status_code=400,
            detail="Could not extract any Agent(name=..., goal=...) definitions from the script.",
        )

    record_id = request.id or str(uuid4())
    record = build_script_record(
        record_id=record_id,
        name=request.name,
        code=request.code,
        agent_configs=agent_configs,
        entry_agent_variable=extract_entry_agent_variable(request.code),
    )
    save_record(SCRIPTS_DIR, record_id, record)
    save_agent_records(agent_configs=agent_configs, source_script_id=record_id)
    return record


@app.get("/agents")
def list_agents() -> list[dict[str, Any]]:
    return load_records(AGENTS_DIR)


@app.post("/agents")
def save_agents(request: AgentSaveRequest) -> list[dict[str, Any]]:
    agent_configs = extract_agent_configs(request.code)
    if not agent_configs:
        raise HTTPException(
            status_code=400,
            detail="Could not extract any Agent(name=..., goal=...) definitions from the script.",
        )

    return save_agent_records(
        agent_configs=agent_configs,
        source_script_id=request.source_script_id,
    )


@app.post("/run")
async def run_agent(request: RunRequest) -> dict[str, str]:
    agent_configs = extract_agent_configs(request.code)
    if not agent_configs:
        await log_to_client("Failed to parse agent parameters from the submitted script.")
        return {
            "status": "error",
            "message": "Could not extract any Agent(name=..., goal=...) definitions from the script.",
        }

    agents = (
        [
            Agent(name=config["name"], goal=config["goal"])
            for config in agent_configs
        ]
    )
    entry_agent_variable = extract_entry_agent_variable(request.code)
    variable_to_name = (
        {
            config["variable"]: config["name"]
            for config in agent_configs
        }
    )
    entry_agent_name = variable_to_name.get(entry_agent_variable) if entry_agent_variable else agents[0].name

    for agent in agents:
        agent.add_to_memory("Agent instantiated from submitted script.")
        await emit_agent_event(
            agent_name=agent.name,
            event_type="state",
            message=f"Instantiated agent '{agent.name}' with goal '{agent.goal}'.",
            state="waiting_for_turn",
            round_number=0,
        )

    runner = WorkflowRunner(
        agents=agents,
        entry_agent_name=entry_agent_name,
        max_rounds=5,
    )
    await runner.run()

    return {
        "status": "ok",
        "message": f"Workflow finished for {len(agents)} agent(s).",
    }


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
