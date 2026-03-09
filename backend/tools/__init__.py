from pathlib import Path

from .read_file import create_read_file
from .search_web import SearchWeb
from .session_files import (
    delete_session_file,
    list_session_files,
    read_session_result_file,
    resolve_session_result_path,
    write_session_file,
)
from .workflow import (
    WORKSPACE_ROOT,
    SESSIONS_ROOT,
    class_name_to_output_pattern,
    create_session,
    get_session_directory,
    get_session_settings,
    get_workflow_run_id,
    get_workflow_session_id,
    initialize_workflow_session,
    read_session_code,
    read_workflow_snapshot,
    record_agent_output,
    record_result_file,
    set_workflow_context,
    set_workflow_run_id,
    set_workflow_session_id,
    sync_workflow_event,
    update_session_settings,
    update_workflow_snapshot,
    write_session_code,
)
from .write_file import create_write_file


def _resolve_path(filename: str, for_write: bool = False) -> Path:
    from .workflow import (
        _normalize_output_path,
        _sanitize_agent_name,
        _workflow_agent_name,
        _workflow_round_number,
    )

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
                workflow_snapshot is not None
                and isinstance(agent_name, str)
                and agent_name != ""
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
            workflow_snapshot is not None
            and isinstance(current_agent_name, str)
            and current_agent_name != ""
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


ReadFile = create_read_file(read_file_tool)
WriteFile = create_write_file(write_file_tool)

TOOL_NAME_TO_DISPLAY: dict[str, str] = {
    "read_file_tool": "ReadFile",
    "write_file_tool": "WriteFile",
    "web_search_tool": "SearchWeb",
}

TOOL_REGISTRY: dict[str, type] = {
    "ReadFile": ReadFile,
    "WriteFile": WriteFile,
    "SearchWeb": SearchWeb,
}
