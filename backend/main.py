from datetime import datetime, UTC
import re
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from runtime import Agent, Workflow, WorkflowRunner


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


@app.post("/run")
async def run_agent(request: RunRequest) -> dict[str, str]:
    agent_configs = extract_agent_configs(request.code)
    if not agent_configs:
        await log_to_client("Failed to parse agent parameters from the submitted script.")
        return {
            "status": "error",
            "message": "Could not extract any Agent(name=..., goal=...) definitions from the script.",
        }

    workflow_config = extract_workflow_config(request.code)
    if workflow_config is None:
        await log_to_client("Failed to parse workflow configuration from the submitted script.")
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
        start_agent_name=start_agent_name,
        max_rounds=workflow.max_rounds,
        connections=connections,
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
