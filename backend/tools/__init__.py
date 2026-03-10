from .read_file import create_read_file
from .search_web import WebSearch
from .session_files import (
    delete_session_file,
    list_session_files,
    read_session_result_file,
    write_session_file,
)
from .workflow import (
    class_name_to_output_pattern,
    create_session,
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


def _normalize_output_filename(filename: str) -> str:
    if not filename.endswith(".md") and not filename.endswith(".txt"):
        return filename if "." in filename else f"{filename}.md"
    if filename.endswith(".txt"):
        return filename[:-4] + ".md"
    return filename


def _resolve_session_file(filename: str, for_write: bool = False) -> tuple[str, str] | None:
    """Resolve filename to (session_id, filename) for session storage. Returns None if not in session context."""
    import re

    from .workflow import (
        _normalize_session_id,
        _sanitize_agent_name,
        _workflow_agent_name,
        _workflow_round_number,
    )

    session_id = get_workflow_session_id()
    if session_id is None:
        return None

    parts = filename.replace("\\", "/").strip("/").split("/")
    if parts and parts[0] == "sessions":
        if len(parts) >= 2:
            sid = parts[1]
            if len(sid) == 32 and all(c in "0123456789abcdef" for c in sid.lower()):
                sid = sid[:6]
            session_id = _normalize_session_id(sid) or session_id
        if len(parts) >= 3:
            safe_name = _normalize_output_filename(parts[-1])
            return (session_id, safe_name)
        return None

    safe_name = parts[-1] if parts else filename
    safe_name = _normalize_output_filename(safe_name)

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
        safe_name = _normalize_output_filename(base_name)
    else:
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
                    safe_name = last_result_file
                    return (session_id, safe_name)
        base = parts[-1] if parts else filename
        base = _normalize_output_filename(base)
        if re.fullmatch(r"^[a-z0-9-]+_\d+\.md$", base):
            safe_name = base
        else:
            prefix = get_workflow_run_id() or session_id
            safe_name = f"{prefix}_{base}"

    return (session_id, safe_name)


def write_file_tool(filename: str, content: str) -> str:
    resolved = _resolve_session_file(filename, for_write=True)
    if resolved is None:
        return "File not found: no session context."
    session_id, safe_name = resolved
    record_result_file(safe_name, content)
    return f"Wrote file: {safe_name}\n\n{content}"


def read_file_tool(filename: str) -> str:
    resolved = _resolve_session_file(filename, for_write=False)
    if resolved is None:
        return "File not found: no session context."
    session_id, safe_name = resolved
    try:
        return read_session_result_file(session_id, safe_name)
    except FileNotFoundError:
        return f"File not found: {safe_name}"


ReadFile = create_read_file(read_file_tool)
WriteFile = create_write_file(write_file_tool)

TOOL_NAME_TO_DISPLAY: dict[str, str] = {
    "read_file_tool": "ReadFile",
    "write_file_tool": "WriteFile",
    "web_search_tool": "WebSearch",
}

TOOL_REGISTRY: dict[str, type] = {
    "ReadFile": ReadFile,
    "WriteFile": WriteFile,
    "WebSearch": WebSearch,
}
