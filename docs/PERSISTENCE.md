# Persistence model

This document describes where session and workflow data is stored and which store is authoritative.

## Canonical source: Supabase

Session and workflow state are **canonical in Supabase** (see `supabase/migrations/` and `backend/db.py`).

| Data | Table / location | Notes |
|------|-------------------|--------|
| Session metadata and workflow snapshot | `sessions.workflow_snapshot` | Status, agent order, current agent/round, per-agent state, settings. |
| Workflow code (single combined script) | `sessions.workflow_code` + `sessions.agent_code` | `workflow_code` is the bottom part (instantiations); `agent_code` is keyed by agent display name, value is class body. |
| Agent output (per round) | `agent_outputs` | `session_id` (UUID FK to sessions), `agent_name`, `round`, `content`. This is the **canonical** store for result files like `analyst_6.md`. |
| Saved agents (templates) | `agents` | Name, role, tools, code. |

Reads for session files (e.g. GET `/sessions/{id}/{filename}`) use Supabase only: workflow and agent code come from `db.read_session_code` / `get_session_code_parts`; result files like `researcher_3.md` come from `db.get_agent_output`.

## Summary

- **Sessions, snapshots, code, and agent outputs**: Supabase is the sole source of truth.
- **No filesystem storage**: The `sessions/` folder is not used. Agent `write_file_tool` and all session file operations read/write via Supabase only. This enables deployment as a web app.
