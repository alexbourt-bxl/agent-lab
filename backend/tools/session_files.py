"""Session file operations: list, read, write, delete."""

from pathlib import Path

from .code_extraction import _extract_workflow_and_agent_code, _get_agent_name_from_class
from .workflow import (
    WORKFLOW_CODE_FILENAME,
    _agent_name_to_kebab,
    _ensure_agent_snapshot,
    kebab_to_class_name,
    read_workflow_snapshot,
    update_workflow_snapshot,
)


def _parse_result_filename(filename: str) -> tuple[str | None, int | None]:
    """Parse analyst_6.md -> (Analyst, 6). Returns (agent_name, round) or (None, None)."""
    import re

    stem = Path(filename).stem
    m = re.match(r"^(.+)_(\d+)$", stem)
    if not m:
        return None, None
    kebab, round_str = m.group(1), m.group(2)
    agent_name = kebab_to_class_name(kebab)
    try:
        return agent_name, int(round_str)
    except ValueError:
        return None, None


def list_session_files(session_id: str) -> list[str]:
    import db as _db

    from .workflow import _normalize_session_id

    resolved_session_id = _normalize_session_id(session_id)
    if resolved_session_id is None:
        raise ValueError("Session ID is required.")

    files: set[str] = set()
    if _db.session_exists(resolved_session_id):
        files.add(WORKFLOW_CODE_FILENAME)
        snapshot = read_workflow_snapshot(resolved_session_id)
        if snapshot:
            for agent_name in snapshot.get("agentOrder", []):
                kebab = _agent_name_to_kebab(agent_name)
                files.add(f"{kebab}.py")
            for agent_name, agent_snap in (snapshot.get("agents") or {}).items():
                if isinstance(agent_snap, dict):
                    for f in agent_snap.get("resultFiles", []):
                        files.add(f)
        outputs = _db.list_agent_outputs(resolved_session_id)
        for o in outputs:
            name = o.get("agent_name")
            rnd = o.get("round")
            if name is not None and rnd is not None:
                kebab = _agent_name_to_kebab(name)
                files.add(f"{kebab}_{rnd}.md")

    return sorted(files)


def read_session_result_file(session_id: str, filename: str) -> str:
    import db as _db

    from .workflow import _normalize_session_id

    resolved_session_id = _normalize_session_id(session_id)
    if resolved_session_id is None:
        raise ValueError("Session ID is required.")

    safe_name = Path(filename).name
    if safe_name == WORKFLOW_CODE_FILENAME:
        code = _db.read_session_code(resolved_session_id)
        workflow_code, agent_code = _extract_workflow_and_agent_code(code)
        return workflow_code

    if safe_name.endswith(".py"):
        code = _db.read_session_code(resolved_session_id)
        _, agent_code = _extract_workflow_and_agent_code(code)
        stem = Path(safe_name).stem
        class_name = kebab_to_class_name(stem)
        return agent_code.get(class_name, "")

    parsed_agent, parsed_round = _parse_result_filename(safe_name)
    if parsed_agent is not None and parsed_round is not None:
        content = _db.get_agent_output(resolved_session_id, parsed_agent, parsed_round)
        if content is not None:
            return content

    raise FileNotFoundError(filename)


def write_session_file(session_id: str, filename: str, content: str) -> None:
    import db as _db

    from .workflow import _normalize_session_id

    resolved_session_id = _normalize_session_id(session_id)
    if resolved_session_id is None:
        raise ValueError("Session ID is required.")

    safe_name = Path(filename).name
    if safe_name == WORKFLOW_CODE_FILENAME:
        _, agent_code = _db.get_session_code_parts(resolved_session_id)
        agent_code_by_name = {_get_agent_name_from_class(b) or k: b for k, b in agent_code.items()}
        _db.write_session_code(resolved_session_id, content, agent_code_by_name)
        return

    if safe_name.endswith(".py"):
        workflow_code, agent_code = _db.get_session_code_parts(resolved_session_id)
        stem = Path(safe_name).stem
        class_name = kebab_to_class_name(stem)
        agent_code[class_name] = content
        agent_code_by_name = {_get_agent_name_from_class(b) or k: b for k, b in agent_code.items()}
        _db.write_session_code(resolved_session_id, workflow_code, agent_code_by_name)
        return

    parsed_agent, parsed_round = _parse_result_filename(safe_name)
    if parsed_agent is not None and parsed_round is not None:
        _db.insert_agent_output(resolved_session_id, parsed_agent, parsed_round, content)

        def apply(s: dict) -> None:
            agent = _ensure_agent_snapshot(s, parsed_agent)
            agent["lastResultFile"] = safe_name
            rfs = agent.setdefault("resultFiles", [])
            if safe_name not in rfs:
                rfs.append(safe_name)

        update_workflow_snapshot(apply, resolved_session_id)
        return

    raise ValueError(
        f"Unsupported file type for session storage: {safe_name}. "
        "Only workflow code, agent code (.py), and agent result files (agent_N.md) are supported."
    )


def delete_session_file(session_id: str, filename: str) -> None:
    import db as _db

    from .code_extraction import _get_agent_name_from_class
    from .workflow import _normalize_session_id

    resolved_session_id = _normalize_session_id(session_id)
    if resolved_session_id is None:
        raise ValueError("Session ID is required.")

    safe_name = Path(filename).name
    if safe_name == WORKFLOW_CODE_FILENAME:
        workflow_code, agent_code = _db.get_session_code_parts(resolved_session_id)
        agent_code_by_name = {_get_agent_name_from_class(b) or k: b for k, b in agent_code.items()}
        _db.write_session_code(resolved_session_id, "", agent_code_by_name)
        return

    if safe_name.endswith(".py"):
        workflow_code, agent_code = _db.get_session_code_parts(resolved_session_id)
        stem = Path(safe_name).stem
        class_name = kebab_to_class_name(stem)
        if class_name in agent_code:
            del agent_code[class_name]
        agent_code_by_name = {_get_agent_name_from_class(b) or k: b for k, b in agent_code.items()}
        _db.write_session_code(resolved_session_id, workflow_code, agent_code_by_name)
        return

    parsed_agent, parsed_round = _parse_result_filename(safe_name)
    if parsed_agent is not None and parsed_round is not None:
        _db.delete_agent_output(resolved_session_id, parsed_agent, parsed_round)

        def apply(s: dict) -> None:
            agent = _ensure_agent_snapshot(s, parsed_agent)
            rfs = agent.get("resultFiles", [])
            if safe_name in rfs:
                agent["resultFiles"] = [f for f in rfs if f != safe_name]
            if agent.get("lastResultFile") == safe_name:
                agent["lastResultFile"] = agent["resultFiles"][-1] if agent["resultFiles"] else None

        update_workflow_snapshot(apply, resolved_session_id)
