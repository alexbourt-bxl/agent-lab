"""Agent routes: list, save, get, delete."""

from typing import Any

from fastapi import APIRouter, HTTPException

from .schemas import SaveAgentRequest

router = APIRouter()


@router.get("")
async def list_agents_endpoint() -> dict[str, Any]:
    import db as _db

    agents = _db.list_agents()
    return {"agents": agents}


@router.post("")
async def save_agent_endpoint(request: SaveAgentRequest) -> dict[str, Any]:
    import db as _db

    agent_id = _db.save_agent(
        name=request.name.strip(),
        role=request.role.strip(),
        tools=request.tools or [],
        code=request.code.strip(),
    )
    return {"id": agent_id}


@router.get("/{agent_id}")
async def get_agent_endpoint(agent_id: str) -> dict[str, Any]:
    import db as _db

    agent = _db.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return agent


@router.delete("/{agent_id}")
async def delete_agent_endpoint(agent_id: str) -> dict[str, str]:
    import db as _db

    _db.delete_agent(agent_id)
    return {"status": "ok"}
