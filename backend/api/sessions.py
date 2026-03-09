"""Session routes: create, settings, files, workflow, get/put/delete file."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from llm import list_available_ollama_models
from tools import (
    create_session,
    delete_session_file,
    get_session_settings,
    list_session_files,
    read_session_result_file,
    read_workflow_snapshot,
    update_session_settings,
    write_session_file,
)

from .schemas import SessionFileUpdateRequest, SettingsUpdateRequest

router = APIRouter()


def _normalize_llm_server(raw: str) -> str:
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    return url.rstrip("/")


def _enrich_snapshot_with_rounds(snapshot: dict[str, Any], session_id: str) -> dict[str, Any]:
    """Add rounds list per agent from agent_outputs for frontend round selector."""
    import db as _db

    try:
        outputs = _db.list_agent_outputs(session_id)
    except Exception:
        return snapshot
    rounds_by_agent: dict[str, list[int]] = {}
    for o in outputs:
        name = o.get("agent_name")
        rnd = o.get("round")
        if name is not None and rnd is not None:
            rounds_by_agent.setdefault(name, []).append(rnd)
    for name, rnds in rounds_by_agent.items():
        rnds.sort()
        agent = (snapshot.get("agents") or {}).get(name)
        if isinstance(agent, dict):
            agent["rounds"] = rnds
    return snapshot


@router.post("/create")
def create_session_endpoint() -> dict[str, str]:
    session_id = create_session()
    return {"sessionId": session_id}


@router.get("/{session_id}/settings")
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


@router.put("/{session_id}/settings")
async def update_session_settings_endpoint(
    session_id: str,
    request: SettingsUpdateRequest,
) -> dict[str, Any]:
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


@router.get("/{session_id}/files")
async def get_session_files(session_id: str) -> dict[str, list[str]]:
    try:
        files = list_session_files(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session.") from None

    return {"files": files}


@router.get("/{session_id}/workflow")
async def get_workflow_session(session_id: str) -> dict[str, Any]:
    snapshot = read_workflow_snapshot(session_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    return _enrich_snapshot_with_rounds(snapshot, session_id)


@router.get("/{session_id}/{filename:path}")
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


@router.put("/{session_id}/{filename:path}")
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


@router.delete("/{session_id}/{filename:path}")
async def delete_session_file_endpoint(session_id: str, filename: str) -> dict[str, str]:
    try:
        delete_session_file(session_id, filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session or filename.") from None

    return {"status": "ok"}
