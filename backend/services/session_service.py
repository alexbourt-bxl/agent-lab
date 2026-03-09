"""Session and settings data for API: enriched snapshot and settings with available models."""

from typing import Any

import db as _db
from llm import list_available_ollama_models

from tools import get_session_settings, read_workflow_snapshot


def _normalize_llm_server(raw: str) -> str:
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    return url.rstrip("/")


def get_workflow_snapshot_enriched(session_id: str) -> dict[str, Any] | None:
    """Return workflow snapshot with rounds list per agent for the frontend round selector."""
    snapshot = read_workflow_snapshot(session_id)
    if snapshot is None:
        return None
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


async def get_settings_for_api(session_id: str) -> dict[str, Any] | None:
    """
    Return settings payload for GET /sessions/{id}/settings:
    provider, model, timeout, llm_server, availableModels.
    Returns None if session not found.
    """
    snapshot = read_workflow_snapshot(session_id)
    if snapshot is None:
        return None
    settings = get_session_settings(session_id)
    llm_server = _normalize_llm_server(
        str(settings.get("llm_server", "http://localhost:11434"))
    )
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


def normalize_llm_server_for_update(raw: str) -> str:
    """Normalize LLM server URL for use in update_session_settings."""
    return _normalize_llm_server(raw)
