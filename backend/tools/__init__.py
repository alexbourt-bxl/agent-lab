from contextvars import ContextVar
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Callable

from storage import DEFAULT_SETTINGS


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
SESSIONS_ROOT = WORKSPACE_ROOT / "sessions"

_workflow_session_id: ContextVar[str | None] = ContextVar(
    "workflow_session_id",
    default=None,
)
_workflow_run_id: ContextVar[str | None] = ContextVar(
    "workflow_run_id",
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


def _normalize_run_id(run_id: str | None) -> str | None:
    if run_id is None:
        return None
    trimmed = run_id.strip()
    if trimmed == "":
        return None
    return trimmed[:6]


def get_workflow_run_id() -> str | None:
    return _normalize_run_id(_workflow_run_id.get())


def set_workflow_run_id(run_id: str | None) -> None:
    _workflow_run_id.set(_normalize_run_id(run_id))


def set_workflow_context(agent_name: str | None, round_number: int | None) -> None:
    _workflow_agent_name.set(agent_name)
    _workflow_round_number.set(round_number)


def _normalize_output_path(target_path: Path) -> Path:
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
        return SESSIONS_ROOT

    return SESSIONS_ROOT / resolved_session_id


WORKFLOW_STATE_FILENAME = "workflow.json"
WORKFLOW_CODE_FILENAME = "workflow.py"


def _agent_name_to_kebab(name: str) -> str:
    result: list[str] = []
    for i, c in enumerate(name):
        if c.isspace():
            if result and result[-1] != "-":
                result.append("-")
        elif c.isupper() and i > 0 and result and result[-1] != "-":
            result.append("-")
            result.append(c.lower())
        elif c.isalnum():
            result.append(c.lower())
    return "".join(result).replace("--", "-").strip("-") or "agent"


def class_name_to_output_pattern(class_name: str) -> str:
    """Derive output file pattern from class name (e.g. Researcher -> researcher_{round}.md)."""
    return f"{_agent_name_to_kebab(class_name)}_{{round}}.md"


def kebab_to_class_name(kebab: str) -> str:
    """Convert kebab filename stem to class name (e.g. researcher -> Researcher)."""
    if not kebab:
        return "Agent"
    return "".join(part.capitalize() for part in kebab.split("-"))


def get_workflow_state_path(session_id: str | None = None) -> Path:
    return get_session_directory(session_id) / WORKFLOW_STATE_FILENAME


def get_workflow_code_path(session_id: str | None = None) -> Path:
    return get_session_directory(session_id) / WORKFLOW_CODE_FILENAME


def get_agent_code_path(agent_name: str, session_id: str | None = None) -> Path:
    kebab = _agent_name_to_kebab(agent_name)
    return get_session_directory(session_id) / f"{kebab}.py"


def get_agent_code_path_by_class_name(class_name: str, session_id: str | None = None) -> Path:
    """Agent files are named by class name (e.g. NewAgent1 -> new-agent-1.py)."""
    kebab = _agent_name_to_kebab(class_name)
    return get_session_directory(session_id) / f"{kebab}.py"


def get_workflow_file_path(session_id: str | None = None) -> Path:
    return get_workflow_state_path(session_id)


def _default_agent_snapshot(agent_name: str, output_file: str = "{round}.md") -> dict[str, Any]:
    now = _utc_now()
    return {
        "name": agent_name,
        "state": "waiting_for_turn",
        "message": "",
        "round": 0,
        "lastResultFile": None,
        "resultFiles": [],
        "outputFile": output_file,
        "stepStartedAt": None,
        "updatedAt": now,
    }


def _default_settings() -> dict[str, Any]:
    return dict(DEFAULT_SETTINGS)


def _default_workflow_snapshot(
    session_id: str,
    agent_order: list[str] | None = None,
    run_id: str | None = None,
    status: str = "running",
) -> dict[str, Any]:
    now = _utc_now()
    ordered_agents = agent_order or []
    return {
        "sessionId": session_id,
        "runId": _normalize_run_id(run_id),
        "status": status,
        "settings": _default_settings(),
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
        legacy_path = get_session_directory(resolved_session_id) / "workflow.md"
        if legacy_path.exists():
            legacy_path.rename(workflow_path)
        else:
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
    for agent_name, agent_data in list(snapshot["agents"].items()):
        if isinstance(agent_data, dict) and "outputFile" not in agent_data:
            agent_data["outputFile"] = "{round}.md"
    if "status" not in snapshot or not isinstance(snapshot["status"], str):
        snapshot["status"] = "running"
    if "runId" not in snapshot:
        snapshot["runId"] = None
    if "settings" not in snapshot or not isinstance(snapshot["settings"], dict):
        snapshot["settings"] = _default_settings()
    else:
        merged = dict(_default_settings())
        merged.update(snapshot["settings"])
        snapshot["settings"] = merged
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


def get_session_settings(session_id: str | None = None) -> dict[str, Any]:
    snapshot = read_workflow_snapshot(session_id)
    if snapshot is None:
        return _default_settings()
    settings = snapshot.get("settings")
    if not isinstance(settings, dict):
        return _default_settings()
    merged = dict(_default_settings())
    merged.update(settings)
    return merged


def update_session_settings(
    settings: dict[str, Any],
    session_id: str | None = None,
) -> None:
    resolved_session_id = _normalize_session_id(session_id) or get_workflow_session_id()
    if resolved_session_id is None:
        return

    def apply(snapshot: dict[str, Any]) -> None:
        current = snapshot.get("settings")
        if not isinstance(current, dict):
            current = _default_settings()
        merged = dict(current)
        merged.update(settings)
        snapshot["settings"] = merged

    update_workflow_snapshot(apply, resolved_session_id)


DEFAULT_SESSION_CODE = '''class Researcher(Agent):
    name = "Researcher"
    role = "Market researcher specializing in SaaS and B2B trends."
    tools = [ReadFile, WriteFile]

class Analyst(Agent):
    name = "Analyst"
    role = "Critical analyst who identifies flaws and improvement opportunities."
    tools = [ReadFile, WriteFile]

researcher = Researcher(
    goal="Find and refine a promising SaaS idea based on analyst feedback",
    input=analyst.output
)

analyst = Analyst(
    goal="Review the researcher's latest SaaS idea and only mark done when the idea is strong enough",
    input=researcher.output
)
'''


def create_session() -> str:
    import uuid

    session_id = uuid.uuid4().hex[:6]
    snapshot = _default_workflow_snapshot(
        session_id,
        agent_order=[],
        run_id=None,
        status="idle",
    )
    _write_workflow_snapshot(snapshot, session_id)
    write_session_code(DEFAULT_SESSION_CODE, session_id)
    initialize_workflow_session(
        session_id,
        agent_order=["Researcher", "Analyst"],
        run_id=None,
        agent_output_files={
            "Researcher": class_name_to_output_pattern("Researcher"),
            "Analyst": class_name_to_output_pattern("Analyst"),
        },
    )
    return session_id


def _pattern_to_regex(pattern: str) -> str:
    """Convert output pattern like 'result_{round}.md' to regex to extract round."""
    import re
    escaped = re.escape(pattern).replace(r"\{round\}", r"(\d+)")
    return escaped


def _rename_agent_result_files(
    session_dir: Path,
    old_pattern: str,
    new_pattern: str,
    result_files: list[str],
    last_result_file: str | None,
) -> tuple[list[str], str | None]:
    """Rename result files when output pattern changes. Returns new result_files and lastResultFile."""
    import re
    regex = _pattern_to_regex(old_pattern)
    new_result_files: list[str] = []
    new_last: str | None = None
    for old_name in result_files:
        match = re.fullmatch(regex, old_name)
        if match:
            round_str = match.group(1)
            new_name = new_pattern.replace("{round}", round_str)
            old_path = session_dir / old_name
            new_path = session_dir / new_name
            if old_path.exists() and old_path != new_path:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                old_path.rename(new_path)
            new_result_files.append(new_name)
            if old_name == last_result_file:
                new_last = new_name
        else:
            new_result_files.append(old_name)
            if old_name == last_result_file:
                new_last = last_result_file
    if new_last is None and last_result_file:
        match = re.fullmatch(regex, last_result_file)
        if match:
            round_str = match.group(1)
            new_last = new_pattern.replace("{round}", round_str)
        else:
            new_last = last_result_file
    return new_result_files, new_last


def initialize_workflow_session(
    session_id: str,
    agent_order: list[str],
    run_id: str | None = None,
    agent_output_files: dict[str, str] | None = None,
) -> None:
    resolved_session_id = _normalize_session_id(session_id)
    if resolved_session_id is None:
        return

    output_files = agent_output_files or {}

    existing = read_workflow_snapshot(resolved_session_id)
    if existing is not None and run_id is not None:
        snapshot = _default_workflow_snapshot(
            resolved_session_id,
            agent_order,
            run_id=run_id,
            status="running",
        )
        snapshot["settings"] = existing.get("settings")
        if not isinstance(snapshot["settings"], dict):
            snapshot["settings"] = _default_settings()
    else:
        snapshot = _default_workflow_snapshot(
            resolved_session_id,
            agent_order,
            run_id=run_id,
            status="running" if run_id else "idle",
        )
        if existing is not None:
            existing_settings = existing.get("settings")
            if isinstance(existing_settings, dict):
                snapshot["settings"] = existing_settings

    session_dir = get_session_directory(resolved_session_id)
    old_agent_order = existing.get("agentOrder", []) if existing else []
    for i, agent_name in enumerate(agent_order):
        output_file = output_files.get(
            agent_name,
            class_name_to_output_pattern(agent_name),
        )
        _ensure_agent_snapshot(snapshot, agent_name)
        snapshot["agents"][agent_name]["outputFile"] = output_file

        if existing is not None and session_dir.exists():
            old_agent_name = old_agent_order[i] if i < len(old_agent_order) else None
            old_agent = existing.get("agents", {}).get(old_agent_name or agent_name)
            old_pattern = old_agent.get("outputFile", "{round}.md") if isinstance(old_agent, dict) else "{round}.md"
            if old_pattern != output_file and old_agent is not None:
                old_result_files = old_agent.get("resultFiles", [])
                old_last = old_agent.get("lastResultFile")
                new_result_files, new_last = _rename_agent_result_files(
                    session_dir,
                    old_pattern,
                    output_file,
                    old_result_files,
                    old_last,
                )
                snapshot["agents"][agent_name]["resultFiles"] = new_result_files
                snapshot["agents"][agent_name]["lastResultFile"] = new_last

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


def list_session_files(session_id: str) -> list[str]:
    resolved_session_id = _normalize_session_id(session_id)
    if resolved_session_id is None:
        raise ValueError("Session ID is required.")

    session_dir = get_session_directory(resolved_session_id)
    if not session_dir.exists():
        return []

    return [f.name for f in session_dir.iterdir() if f.is_file()]


def resolve_session_result_path(session_id: str, filename: str) -> Path:
    resolved_session_id = _normalize_session_id(session_id)
    if resolved_session_id is None:
        raise ValueError("Session ID is required.")

    safe_filename = Path(filename).name
    return get_session_directory(resolved_session_id) / safe_filename


def _extract_workflow_and_agent_code(code: str) -> tuple[str, dict[str, str]]:
    """Extract workflow code and agent class code from combined code."""
    import re

    workflow_code = ""
    agent_code: dict[str, str] = {}

    class_matches = list(re.finditer(r"class (\w+)\(Agent\):\s*", code))
    for i, match in enumerate(class_matches):
        class_name = match.group(1)
        body_start = match.end()
        next_class = re.search(r"\nclass \w+\(Agent\)", code[body_start:])
        next_inst = re.search(r"\n([A-Za-z_]\w*)\s*=\s*\w+\s*\(", code[body_start:])
        class_end = len(code)
        if next_class and next_inst:
            class_end = body_start + min(next_class.start(), next_inst.start())
        elif next_class:
            class_end = body_start + next_class.start()
        elif next_inst:
            class_end = body_start + next_inst.start()
        elif i + 1 < len(class_matches):
            class_end = class_matches[i + 1].start()
        class_block = code[match.start() : class_end].strip()
        agent_code[class_name] = class_block

    first_inst = re.search(r"\n([A-Za-z_]\w*)\s*=\s*\w+\s*\(", code)
    if first_inst:
        workflow_code = code[first_inst.start() :].lstrip()
    elif not class_matches:
        workflow_code = code.strip()

    return workflow_code, agent_code


def _get_agent_name_from_class(class_code: str) -> str | None:
    """Extract agent display name from class body (name attr or class name)."""
    import re

    match = re.search(r'name\s*=\s*["\']([^"\']*)["\']', class_code)
    if match and match.group(1).strip():
        return match.group(1).strip()
    match = re.search(r"class (\w+)\(Agent\)", class_code)
    return match.group(1) if match else None


def write_session_code(code: str, session_id: str | None = None) -> None:
    resolved_session_id = _normalize_session_id(session_id) or get_workflow_session_id()
    if resolved_session_id is None:
        return

    session_dir = get_session_directory(resolved_session_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    workflow_code, agent_code = _extract_workflow_and_agent_code(code)

    workflow_path = get_workflow_code_path(resolved_session_id)
    workflow_path.write_text(workflow_code, encoding="utf-8")

    for class_name, class_body in agent_code.items():
        agent_path = get_agent_code_path_by_class_name(class_name, resolved_session_id)
        agent_path.write_text(class_body, encoding="utf-8")


def read_session_code(session_id: str) -> str:
    resolved_session_id = _normalize_session_id(session_id)
    if resolved_session_id is None:
        raise FileNotFoundError("Session not found.")

    session_dir = get_session_directory(resolved_session_id)
    if not session_dir.exists():
        raise FileNotFoundError(str(session_dir))

    workflow_path = get_workflow_code_path(resolved_session_id)
    workflow_code = (
        workflow_path.read_text(encoding="utf-8")
        if workflow_path.exists()
        else ""
    )

    snapshot = read_workflow_snapshot(resolved_session_id)
    agent_order = snapshot.get("agentOrder", []) if snapshot else []

    agent_parts_by_name: list[tuple[str, str]] = []
    seen: set[str] = set()

    for path in sorted(session_dir.glob("*.py")):
        if path.name == WORKFLOW_CODE_FILENAME:
            continue
        content = path.read_text(encoding="utf-8")
        agent_name = _get_agent_name_from_class(content)
        if agent_name and agent_name not in seen:
            seen.add(agent_name)
            agent_parts_by_name.append((agent_name, content))

    name_to_content = {n: c for (n, c) in agent_parts_by_name}
    ordered = [name_to_content[name] for name in agent_order if name in name_to_content]
    remaining = [c for (n, c) in agent_parts_by_name if n not in agent_order]
    agent_parts = ordered + remaining

    combined = "\n\n".join(agent_parts)
    if workflow_code:
        combined = (combined + "\n\n" + workflow_code) if combined else workflow_code
    return combined


def read_session_result_file(session_id: str, filename: str) -> str:
    target_path = resolve_session_result_path(session_id, filename)
    if not target_path.exists():
        raise FileNotFoundError(target_path)

    return target_path.read_text(encoding="utf-8")


def _apply_agent_output_rename(session_id: str, filename: str, content: str) -> None:
    """When an agent class is renamed, rename result files to match the new class name."""
    import re

    if not filename.endswith(".py") or filename == "workflow.py":
        return
    old_class_name = kebab_to_class_name(Path(filename).stem)
    class_match = re.search(r"class\s+(\w+)\s*\(\s*Agent\s*\)", content)
    if not class_match:
        return
    new_class_name = class_match.group(1)
    if old_class_name == new_class_name:
        return
    old_pattern = class_name_to_output_pattern(old_class_name)
    new_pattern = class_name_to_output_pattern(new_class_name)
    snapshot = read_workflow_snapshot(session_id)
    if snapshot is None:
        return
    agents = snapshot.get("agents", {})
    agent_name = None
    agent_snapshot = None
    for name, data in agents.items():
        if isinstance(data, dict) and data.get("outputFile") == old_pattern:
            agent_name = name
            agent_snapshot = data
            break
    if agent_name is None or agent_snapshot is None:
        return
    session_dir = get_session_directory(session_id)
    if not session_dir.exists():
        return
    result_files = agent_snapshot.get("resultFiles", [])
    last_result_file = agent_snapshot.get("lastResultFile")
    new_result_files, new_last = _rename_agent_result_files(
        session_dir,
        old_pattern,
        new_pattern,
        result_files,
        last_result_file,
    )

    def apply(s: dict[str, Any]) -> None:
        agent = _ensure_agent_snapshot(s, agent_name)
        agent["outputFile"] = new_pattern
        agent["resultFiles"] = new_result_files
        agent["lastResultFile"] = new_last

    update_workflow_snapshot(apply, session_id)


def write_session_file(session_id: str, filename: str, content: str) -> None:
    target_path = resolve_session_result_path(session_id, filename)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    _apply_agent_output_rename(session_id, filename, content)


def delete_session_file(session_id: str, filename: str) -> None:
    target_path = resolve_session_result_path(session_id, filename)
    if target_path.exists():
        target_path.unlink()


def _resolve_path(filename: str, for_write: bool = False) -> Path:
    target_path = Path(filename)

    if target_path.is_absolute():
        return _normalize_output_path(target_path)

    session_id = get_workflow_session_id()
    if target_path.parts and target_path.parts[0] == "sessions":
        parts = list(target_path.parts)
        if len(parts) >= 2 and len(parts[1]) == 32 and all(c in "0123456789abcdef" for c in parts[1].lower()):
            parts[1] = parts[1][:6]
        return _normalize_output_path(WORKSPACE_ROOT / Path(*parts))
    if session_id:
        if for_write:
            agent_name = _sanitize_agent_name(_workflow_agent_name.get() or "agent")
            round_number = _workflow_round_number.get()
            round_str = str(round_number) if round_number is not None else "0"
            workflow_snapshot = read_workflow_snapshot(session_id)
            output_pattern = "{round}.md"
            if (
                workflow_snapshot is not None and
                isinstance(agent_name, str) and
                agent_name != ""
            ):
                agent_snapshot = workflow_snapshot.get("agents", {}).get(agent_name)
                if isinstance(agent_snapshot, dict):
                    output_pattern = agent_snapshot.get("outputFile", "{round}.md")
            base_name = str(output_pattern).replace("{round}", round_str)
            return SESSIONS_ROOT / session_id / _normalize_output_path(Path(base_name))
        target_path = _normalize_output_path(target_path)
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
                    return SESSIONS_ROOT / session_id / last_result_file
        prefix = get_workflow_run_id() or session_id
        return SESSIONS_ROOT / session_id / f"{prefix}_{target_path.name}"
    return _normalize_output_path(SESSIONS_ROOT / target_path)


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


# --- Concrete tools ---

from .read_file import create_read_file
from .write_file import create_write_file
from .search_web import SearchWeb

ReadFile = create_read_file(read_file_tool)
WriteFile = create_write_file(write_file_tool)

TOOL_REGISTRY: dict[str, type] = {
    "ReadFile": ReadFile,
    "WriteFile": WriteFile,
    "SearchWeb": SearchWeb,
}
