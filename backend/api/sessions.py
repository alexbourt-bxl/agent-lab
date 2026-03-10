"""Session routes: create, settings, files, workflow, get/put/delete file."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

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

from services import get_settings_for_api, get_workflow_snapshot_enriched
from services.session_service import normalize_llm_server_for_update

from .schemas import SessionFileUpdateRequest, SettingsUpdateRequest

router = APIRouter()


@router.post("/create")
def create_session_endpoint() -> dict[str, str]:
    session_id = create_session()
    return {"sessionId": session_id}


@router.get("/{session_id}/settings")
async def get_session_settings_endpoint(session_id: str) -> dict[str, Any]:
    settings_payload = await get_settings_for_api(session_id)
    if settings_payload is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return settings_payload


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
            "llm_server": normalize_llm_server_for_update(llm_server),
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
    snapshot = get_workflow_snapshot_enriched(session_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    return snapshot


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
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session or filename.") from None

    return {"status": "ok"}


@router.delete("/{session_id}/{filename:path}")
async def delete_session_file_endpoint(session_id: str, filename: str) -> dict[str, str]:
    try:
        delete_session_file(session_id, filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session or filename.") from None

    return {"status": "ok"}
