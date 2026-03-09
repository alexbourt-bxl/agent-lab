"""Per-session workflow run state: cancellation events keyed by session_id."""

import asyncio

# Registry of active run cancel events: session_id -> Event.
# Only one run per session at a time; the event is created at run start and removed at run end.
_cancel_events: dict[str, asyncio.Event] = {}


def register_cancel_event(session_id: str) -> asyncio.Event:
    """Create and register a cancel event for this session. Clear it so a fresh run can start."""
    ev = asyncio.Event()
    _cancel_events[session_id] = ev
    return ev


def unregister_cancel_event(session_id: str) -> None:
    """Remove the cancel event for this session (call when run ends)."""
    _cancel_events.pop(session_id, None)


def request_cancel(session_id: str | None = None) -> None:
    """
    Request cancellation of a run.
    If session_id is given, only that session's run is cancelled.
    If session_id is None, all registered runs are requested to cancel (e.g. legacy /stop with no body).
    """
    if session_id is not None:
        if session_id in _cancel_events:
            _cancel_events[session_id].set()
        return
    for ev in _cancel_events.values():
        ev.set()


# Legacy global event for backward compatibility where callers still use cancel_requested.
# Prefer passing a per-run event into WorkflowRunner.run() and using request_cancel(session_id).
cancel_requested: asyncio.Event = asyncio.Event()
