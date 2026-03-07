from contextvars import ContextVar
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Callable


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
RESULTS_ROOT = WORKSPACE_ROOT / "results"

_workflow_session_id: ContextVar[str | None] = ContextVar(
    "workflow_session_id",
    default=None,
)
_workflow_agent_name: ContextVar[str | None] = ContextVar(
    "workflow_agent_name",
    default=None,
)
_workflow_round_number: ContextVar[int | None] = ContextVar(
    "workflow_round_number",
    default=None,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_session_id(session_id: str | None) -> str | None:
    if session_id is None:
        return None

    trimmed = session_id.strip()
    if trimmed == "":
        return None

    return trimmed[:6]


def get_workflow_session_id() -> str | None:
    return _normalize_session_id(_workflow_session_id.get())


def set_workflow_session_id(session_id: str | None) -> None:
    _workflow_session_id.set(_normalize_session_id(session_id))


def set_workflow_context(agent_name: str | None, round_number: int | None) -> None:
    _workflow_agent_name.set(agent_name)
    _workflow_round_number.set(round_number)


def _normalize_results_path(target_path: Path) -> Path:
    if target_path.suffix == "":
        target_path = target_path.with_suffix(".md")
    elif target_path.suffix == ".txt":
        target_path = target_path.with_suffix(".md")

    return target_path


def _sanitize_agent_name(agent_name: str) -> str:
    sanitized = "".join(c if c.isalnum() or c in "-_" else "_" for c in agent_name)
    return sanitized or "agent"


def get_session_directory(session_id: str | None = None) -> Path:
    resolved_session_id = _normalize_session_id(session_id) or get_workflow_session_id()
    if resolved_session_id is None:
        return RESULTS_ROOT

    return RESULTS_ROOT / resolved_session_id


def get_workflow_file_path(session_id: str | None = None) -> Path:
    return get_session_directory(session_id) / "workflow.md"


def _default_agent_snapshot(agent_name: str) -> dict[str, Any]:
    now = _utc_now()
    return {
        "name": agent_name,
        "state": "waiting_for_turn",
        "message": "",
        "round": 0,
        "lastResultFile": None,
        "resultFiles": [],
        "stepStartedAt": None,
        "updatedAt": now,
    }


def _default_workflow_snapshot(session_id: str, agent_order: list[str] | None = None) -> dict[str, Any]:
    now = _utc_now()
    ordered_agents = agent_order or []
    return {
        "sessionId": session_id,
        "status": "running",
        "agentOrder": ordered_agents,
        "currentAgent": None,
        "currentRound": 0,
        "startedAt": now,
        "updatedAt": now,
        "workflowResult": None,
        "workflowResultFile": None,
        "agents": {
            agent_name: _default_agent_snapshot(agent_name)
            for agent_name in ordered_agents
        },
    }


def _write_workflow_snapshot(snapshot: dict[str, Any], session_id: str | None = None) -> None:
    resolved_session_id = _normalize_session_id(session_id) or str(snapshot.get("sessionId", "")).strip()[:6]
    if resolved_session_id == "":
        return

    snapshot["sessionId"] = resolved_session_id
    snapshot["updatedAt"] = _utc_now()
    workflow_path = get_workflow_file_path(resolved_session_id)
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def read_workflow_snapshot(session_id: str | None = None) -> dict[str, Any] | None:
    resolved_session_id = _normalize_session_id(session_id) or get_workflow_session_id()
    if resolved_session_id is None:
        return None

    workflow_path = get_workflow_file_path(resolved_session_id)
    if not workflow_path.exists():
        return None

    try:
        snapshot = json.loads(workflow_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    if not isinstance(snapshot, dict):
        return None

    snapshot["sessionId"] = resolved_session_id
    if "agentOrder" not in snapshot or not isinstance(snapshot["agentOrder"], list):
        snapshot["agentOrder"] = []
    if "agents" not in snapshot or not isinstance(snapshot["agents"], dict):
        snapshot["agents"] = {}
    if "status" not in snapshot or not isinstance(snapshot["status"], str):
        snapshot["status"] = "running"
    if "workflowResult" not in snapshot:
        snapshot["workflowResult"] = None
    if "workflowResultFile" not in snapshot:
        snapshot["workflowResultFile"] = None
    if "currentAgent" not in snapshot:
        snapshot["currentAgent"] = None
    if "currentRound" not in snapshot:
        snapshot["currentRound"] = 0
    if "startedAt" not in snapshot:
        snapshot["startedAt"] = None
    if "updatedAt" not in snapshot:
        snapshot["updatedAt"] = None

    for agent_name in snapshot["agentOrder"]:
        agents = snapshot["agents"]
        if agent_name not in agents or not isinstance(agents[agent_name], dict):
            agents[agent_name] = _default_agent_snapshot(agent_name)

    return snapshot


def initialize_workflow_session(session_id: str, agent_order: list[str]) -> None:
    resolved_session_id = _normalize_session_id(session_id)
    if resolved_session_id is None:
        return

    snapshot = _default_workflow_snapshot(resolved_session_id, agent_order)
    _write_workflow_snapshot(snapshot, resolved_session_id)


def _ensure_agent_snapshot(snapshot: dict[str, Any], agent_name: str) -> dict[str, Any]:
    agents = snapshot.setdefault("agents", {})
    if not isinstance(agents, dict):
        agents = {}
        snapshot["agents"] = agents

    if agent_name not in agents or not isinstance(agents[agent_name], dict):
        agents[agent_name] = _default_agent_snapshot(agent_name)

    agent_snapshot = agents[agent_name]
    if agent_name not in snapshot.get("agentOrder", []):
        snapshot.setdefault("agentOrder", []).append(agent_name)

    agent_snapshot["name"] = agent_name
    agent_snapshot.setdefault("resultFiles", [])
    agent_snapshot.setdefault("lastResultFile", None)
    agent_snapshot.setdefault("stepStartedAt", None)
    agent_snapshot.setdefault("updatedAt", _utc_now())
    agent_snapshot.setdefault("round", 0)
    agent_snapshot.setdefault("message", "")
    agent_snapshot.setdefault("state", "waiting_for_turn")
    return agent_snapshot


def update_workflow_snapshot(
    updater: Callable[[dict[str, Any]], None],
    session_id: str | None = None,
) -> None:
    resolved_session_id = _normalize_session_id(session_id) or get_workflow_session_id()
    if resolved_session_id is None:
        return

    snapshot = read_workflow_snapshot(resolved_session_id)
    if snapshot is None:
        snapshot = _default_workflow_snapshot(resolved_session_id)

    updater(snapshot)
    _write_workflow_snapshot(snapshot, resolved_session_id)


def sync_workflow_event(
    event_type: str,
    message: str,
    state: str | None = None,
    agent_name: str | None = None,
    round_number: int | None = None,
    agent_order: list[str] | None = None,
    session_id: str | None = None,
) -> None:
    resolved_session_id = _normalize_session_id(session_id) or get_workflow_session_id()
    if resolved_session_id is None:
        return

    def apply(snapshot: dict[str, Any]) -> None:
        now = _utc_now()

        if agent_order is not None:
            snapshot["agentOrder"] = agent_order
            for ordered_agent_name in agent_order:
                _ensure_agent_snapshot(snapshot, ordered_agent_name)

        if event_type == "workflow_started":
            snapshot["status"] = "running"
            if snapshot.get("startedAt") is None:
                snapshot["startedAt"] = now

        if event_type in {"workflow_result", "system"} and state in {"done", "stopped", "error", "running"}:
            snapshot["status"] = state

        if round_number is not None:
            snapshot["currentRound"] = round_number

        if agent_name is not None:
            agent_snapshot = _ensure_agent_snapshot(snapshot, agent_name)
            previous_state = str(agent_snapshot.get("state", ""))

            if state is not None:
                agent_snapshot["state"] = state
            agent_snapshot["message"] = message
            if round_number is not None:
                agent_snapshot["round"] = round_number
            if state in {"thinking", "working"}:
                if previous_state != state or agent_snapshot.get("stepStartedAt") is None:
                    agent_snapshot["stepStartedAt"] = now
            elif state is not None:
                agent_snapshot["stepStartedAt"] = None

            agent_snapshot["updatedAt"] = now
            snapshot["currentAgent"] = agent_name

        if event_type == "workflow_result":
            snapshot["workflowResult"] = message
            current_agent_name = snapshot.get("currentAgent")
            if isinstance(current_agent_name, str) and current_agent_name != "":
                current_agent_snapshot = _ensure_agent_snapshot(snapshot, current_agent_name)
                workflow_result_file = current_agent_snapshot.get("lastResultFile")
                if isinstance(workflow_result_file, str) and workflow_result_file != "":
                    snapshot["workflowResultFile"] = workflow_result_file

    update_workflow_snapshot(apply, resolved_session_id)


def record_agent_output(
    agent_name: str,
    session_id: str | None = None,
) -> None:
    def apply(snapshot: dict[str, Any]) -> None:
        agent_snapshot = _ensure_agent_snapshot(snapshot, agent_name)
        agent_snapshot["updatedAt"] = _utc_now()
        snapshot["currentAgent"] = agent_name

    update_workflow_snapshot(apply, session_id)


def record_result_file(
    filename: str,
    content: str,
    session_id: str | None = None,
    agent_name: str | None = None,
    round_number: int | None = None,
) -> None:
    resolved_agent_name = agent_name or _workflow_agent_name.get()
    resolved_round_number = round_number if round_number is not None else _workflow_round_number.get()
    if resolved_agent_name is None:
        return

    def apply(snapshot: dict[str, Any]) -> None:
        agent_snapshot = _ensure_agent_snapshot(snapshot, resolved_agent_name)
        agent_snapshot["lastResultFile"] = filename
        result_files = agent_snapshot.setdefault("resultFiles", [])
        if filename not in result_files:
            result_files.append(filename)
        if resolved_round_number is not None:
            agent_snapshot["round"] = resolved_round_number
            snapshot["currentRound"] = resolved_round_number
        agent_snapshot["updatedAt"] = _utc_now()
        snapshot["currentAgent"] = resolved_agent_name

    update_workflow_snapshot(apply, session_id)


def resolve_session_result_path(session_id: str, filename: str) -> Path:
    resolved_session_id = _normalize_session_id(session_id)
    if resolved_session_id is None:
        raise ValueError("Session ID is required.")

    safe_filename = Path(filename).name
    return get_session_directory(resolved_session_id) / safe_filename


SESSION_CODE_FILENAME = "code.py"


def get_session_code_path(session_id: str | None = None) -> Path | None:
    resolved_session_id = _normalize_session_id(session_id) or get_workflow_session_id()
    if resolved_session_id is None:
        return None
    return get_session_directory(resolved_session_id) / SESSION_CODE_FILENAME


def write_session_code(code: str, session_id: str | None = None) -> None:
    path = get_session_code_path(session_id)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")


def read_session_code(session_id: str) -> str:
    path = get_session_code_path(session_id)
    if path is None:
        raise FileNotFoundError("Session not found.")
    if not path.exists():
        raise FileNotFoundError(str(path))
    return path.read_text(encoding="utf-8")


def read_session_result_file(session_id: str, filename: str) -> str:
    target_path = resolve_session_result_path(session_id, filename)
    if not target_path.exists():
        raise FileNotFoundError(target_path)

    return target_path.read_text(encoding="utf-8")


def _resolve_path(filename: str, for_write: bool = False) -> Path:
    target_path = Path(filename)

    if target_path.is_absolute():
        return _normalize_results_path(target_path)

    session_id = get_workflow_session_id()
    if target_path.parts and target_path.parts[0] == "results":
        parts = list(target_path.parts)
        if len(parts) >= 2 and len(parts[1]) == 32 and all(c in "0123456789abcdef" for c in parts[1].lower()):
            parts[1] = parts[1][:6]
        return _normalize_results_path(WORKSPACE_ROOT / Path(*parts))
    if session_id:
        if for_write:
            agent_name = _sanitize_agent_name(_workflow_agent_name.get() or "agent")
            round_number = _workflow_round_number.get()
            round_str = str(round_number) if round_number is not None else "0"
            base_name = f"{session_id}_{agent_name}_{round_str}"
            return RESULTS_ROOT / session_id / _normalize_results_path(Path(base_name))
        target_path = _normalize_results_path(target_path)
        stem_parts = target_path.stem.split("_")
        if len(stem_parts) >= 3 and len(stem_parts[0]) >= 6:
            read_session_id = stem_parts[0][:6]
            return RESULTS_ROOT / read_session_id / target_path.name
        workflow_snapshot = read_workflow_snapshot(session_id)
        current_agent_name = _workflow_agent_name.get()
        if (
            workflow_snapshot is not None and
            isinstance(current_agent_name, str) and
            current_agent_name != ""
        ):
            agent_snapshot = workflow_snapshot.get("agents", {}).get(current_agent_name)
            if isinstance(agent_snapshot, dict):
                last_result_file = agent_snapshot.get("lastResultFile")
                if isinstance(last_result_file, str) and last_result_file != "":
                    return RESULTS_ROOT / session_id / last_result_file
        return RESULTS_ROOT / session_id / f"{session_id}_{target_path.name}"
    return _normalize_results_path(RESULTS_ROOT / target_path)


def write_file_tool(filename: str, content: str) -> str:
    target_path = _resolve_path(filename, for_write=True)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    record_result_file(target_path.name, content)
    return f"Wrote file: {target_path}\n\n{content}"


def read_file_tool(filename: str) -> str:
    target_path = _resolve_path(filename)

    if not target_path.exists():
        return f"File not found: {target_path}"

    return target_path.read_text(encoding="utf-8")
