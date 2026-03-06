from contextvars import ContextVar
from pathlib import Path


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


def set_workflow_session_id(session_id: str | None) -> None:
    _workflow_session_id.set(session_id)


def set_workflow_context(agent_name: str | None, round_number: int | None) -> None:
    _workflow_agent_name.set(agent_name)
    _workflow_round_number.set(round_number)


def _normalize_results_path(target_path: Path) -> Path:
    if target_path.suffix == "":
        target_path = target_path.with_suffix(".md")
    elif target_path.suffix == ".txt":
        target_path = target_path.with_suffix(".md")

    return target_path


def _resolve_path(filename: str, for_write: bool = False) -> Path:
    target_path = Path(filename)

    if target_path.is_absolute():
        return _normalize_results_path(target_path)

    raw_session_id = _workflow_session_id.get()
    session_id = (raw_session_id or "")[:6] if raw_session_id else None
    if target_path.parts and target_path.parts[0] == "results":
        parts = list(target_path.parts)
        if len(parts) >= 2 and len(parts[1]) == 32 and all(c in "0123456789abcdef" for c in parts[1].lower()):
            parts[1] = parts[1][:6]
        return _normalize_results_path(WORKSPACE_ROOT / Path(*parts))
    if session_id:
        if for_write:
            agent_name = _workflow_agent_name.get() or "agent"
            agent_safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in agent_name)
            round_number = _workflow_round_number.get()
            round_str = str(round_number) if round_number is not None else "0"
            base_name = f"{session_id}_{agent_safe}_{round_str}"
            return RESULTS_ROOT / session_id / _normalize_results_path(Path(base_name))
        target_path = _normalize_results_path(target_path)
        stem_parts = target_path.stem.split("_")
        if len(stem_parts) >= 3 and len(stem_parts[0]) >= 6:
            read_session_id = stem_parts[0][:6]
            return RESULTS_ROOT / read_session_id / target_path.name
        return RESULTS_ROOT / session_id / f"{session_id}_{target_path.name}"
    return _normalize_results_path(RESULTS_ROOT / target_path)


def write_file_tool(filename: str, content: str) -> str:
    target_path = _resolve_path(filename, for_write=True)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    return f"Wrote file: {target_path}\n\n{content}"


def read_file_tool(filename: str) -> str:
    target_path = _resolve_path(filename)

    if not target_path.exists():
        return f"File not found: {target_path}"

    return target_path.read_text(encoding="utf-8")
