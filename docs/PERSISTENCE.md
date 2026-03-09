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

Reads for session files (e.g. GET `/sessions/{id}/{filename}`) prefer Supabase: workflow and agent code come from `db.read_session_code` / `get_session_code_parts`; result files like `researcher_3.md` come from `db.get_agent_output`. The filesystem is only used as a fallback for result files that are not yet (or no longer) in the DB.

## Filesystem (secondary)

- **`sessions/<session_id>/`** – Optional on-disk copies. Used by the agent `write_file_tool` when writing output (content is also written to `agent_outputs` via `record_result_file`). Listing and reading may include these files; listing merges DB-derived filenames with directory contents.
- **Delete behavior** – `delete_session_file` currently only removes the file from the filesystem. It does not remove the corresponding row from `agent_outputs` or update the workflow snapshot. So for result files, the DB remains the source of truth after a "delete" from the API.

## Summary

- **Sessions, snapshots, code, and agent outputs**: Supabase is the source of truth.
- **Files under `sessions/<id>/`**: Optional mirror/legacy; agent outputs are written to both DB and (when using the file tool) disk. Deletes only affect disk.
