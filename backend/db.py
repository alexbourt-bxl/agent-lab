"""Supabase storage for sessions, agent_outputs, and agents."""

import os
from typing import Any


def _get_client():
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54321")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not key:
        key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not key:
        raise RuntimeError(
            "SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY required. "
            "Run 'supabase start' and use 'supabase status' for keys."
        )
    return create_client(url, key)


def _session_row_by_id(session_id: str) -> dict[str, Any] | None:
    client = _get_client()
    r = client.table("sessions").select("id").eq("session_id", session_id).execute()
    if not r.data or len(r.data) == 0:
        return None
    return r.data[0]


def session_exists(session_id: str) -> bool:
    return _session_row_by_id(session_id) is not None


def read_workflow_snapshot(session_id: str) -> dict[str, Any] | None:
    client = _get_client()
    r = client.table("sessions").select("workflow_snapshot").eq("session_id", session_id).execute()
    if not r.data or len(r.data) == 0:
        return None
    snap = r.data[0].get("workflow_snapshot")
    if not isinstance(snap, dict):
        return None
    snap["sessionId"] = session_id
    return snap


def write_workflow_snapshot(session_id: str, snapshot: dict[str, Any]) -> None:
    from datetime import UTC, datetime

    snapshot["sessionId"] = session_id
    snapshot["updatedAt"] = datetime.now(UTC).isoformat()
    client = _get_client()
    row = _session_row_by_id(session_id)
    if row:
        client.table("sessions").update({
            "workflow_snapshot": snapshot,
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("id", row["id"]).execute()
    else:
        client.table("sessions").insert({
            "session_id": session_id,
            "workflow_snapshot": snapshot,
        }).execute()


def get_session_code_parts(session_id: str) -> tuple[str, dict[str, str]]:
    """Return (workflow_code, agent_code dict)."""
    client = _get_client()
    r = client.table("sessions").select("workflow_snapshot, workflow_code, agent_code").eq("session_id", session_id).execute()
    if not r.data or len(r.data) == 0:
        raise FileNotFoundError(f"Session {session_id} not found")
    row = r.data[0]
    workflow_code = row.get("workflow_code") or ""
    agent_code = row.get("agent_code") or {}
    if not isinstance(agent_code, dict):
        agent_code = {}
    return workflow_code, agent_code


def read_session_code(session_id: str) -> str:
    workflow_code, agent_code = get_session_code_parts(session_id)
    client = _get_client()
    r = client.table("sessions").select("workflow_snapshot").eq("session_id", session_id).execute()
    agent_order = []
    if r.data and len(r.data) > 0:
        agent_order = (r.data[0].get("workflow_snapshot") or {}).get("agentOrder") or []
    ordered = [agent_code.get(name, "") for name in agent_order if name in agent_code]
    remaining = [agent_code[name] for name in agent_code if name not in agent_order]
    agent_parts = ordered + remaining
    combined = "\n\n".join(p for p in agent_parts if p)
    if workflow_code:
        combined = (combined + "\n\n" + workflow_code) if combined else workflow_code
    return combined


def write_session_code(session_id: str, workflow_code: str, agent_code: dict[str, str]) -> None:
    client = _get_client()
    row = _session_row_by_id(session_id)
    if row:
        client.table("sessions").update({
            "workflow_code": workflow_code,
            "agent_code": agent_code,
        }).eq("id", row["id"]).execute()
    else:
        client.table("sessions").insert({
            "session_id": session_id,
            "workflow_code": workflow_code,
            "agent_code": agent_code,
        }).execute()


def insert_agent_output(session_id: str, agent_name: str, round_num: int, content: str) -> None:
    row = _session_row_by_id(session_id)
    if not row:
        return
    client = _get_client()
    session_uuid = row["id"]
    client.table("agent_outputs").delete().eq(
        "session_id", session_uuid
    ).eq("agent_name", agent_name).eq("round", round_num).execute()
    client.table("agent_outputs").insert({
        "session_id": session_uuid,
        "agent_name": agent_name,
        "round": round_num,
        "content": content,
    }).execute()


def get_agent_output(session_id: str, agent_name: str, round_num: int) -> str | None:
    row = _session_row_by_id(session_id)
    if not row:
        return None
    client = _get_client()
    r = client.table("agent_outputs").select("content").eq(
        "session_id", row["id"]
    ).eq("agent_name", agent_name).eq("round", round_num).execute()
    if not r.data or len(r.data) == 0:
        return None
    return r.data[0].get("content")


def get_latest_agent_output(session_id: str, agent_name: str) -> str | None:
    row = _session_row_by_id(session_id)
    if not row:
        return None
    client = _get_client()
    r = client.table("agent_outputs").select("content").eq(
        "session_id", row["id"]
    ).eq("agent_name", agent_name).order("round", desc=True).limit(1).execute()
    if not r.data or len(r.data) == 0:
        return None
    return r.data[0].get("content")


def list_agent_outputs(session_id: str) -> list[dict[str, Any]]:
    row = _session_row_by_id(session_id)
    if not row:
        return []
    client = _get_client()
    r = client.table("agent_outputs").select("agent_name, round, created_at").eq(
        "session_id", row["id"]
    ).order("round", desc=False).execute()
    return r.data or []


def create_session(session_id: str, workflow_snapshot: dict[str, Any], workflow_code: str, agent_code: dict[str, str]) -> None:
    client = _get_client()
    client.table("sessions").insert({
        "session_id": session_id,
        "workflow_snapshot": workflow_snapshot,
        "workflow_code": workflow_code,
        "agent_code": agent_code,
    }).execute()


def list_agents() -> list[dict[str, Any]]:
    client = _get_client()
    r = client.table("agents").select("*").order("created_at", desc=True).execute()
    return r.data or []


def get_agent(agent_id: str) -> dict[str, Any] | None:
    client = _get_client()
    r = client.table("agents").select("*").eq("id", agent_id).execute()
    if not r.data or len(r.data) == 0:
        return None
    return r.data[0]


def save_agent(name: str, role: str, tools: list[str], code: str) -> str:
    client = _get_client()
    r = client.table("agents").insert({
        "name": name,
        "role": role,
        "tools": tools,
        "code": code,
    }).execute()
    if not r.data or len(r.data) == 0:
        raise RuntimeError("Failed to save agent")
    return r.data[0]["id"]


def delete_agent(agent_id: str) -> None:
    client = _get_client()
    client.table("agents").delete().eq("id", agent_id).execute()
