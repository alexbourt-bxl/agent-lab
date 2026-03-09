"""Normalized turn-result and handoff schema for agent workflow decisions."""

from typing import Any


# Valid status values for agent turn completion
TURN_STATUS_CONTINUE = "continue"
TURN_STATUS_REVISE = "revise"
TURN_STATUS_APPROVED = "approved"
TURN_STATUS_FINAL = "final"

VALID_TURN_STATUSES = frozenset(
    {
        TURN_STATUS_CONTINUE,
        TURN_STATUS_REVISE,
        TURN_STATUS_APPROVED,
        TURN_STATUS_FINAL,
    }
)

# Valid handoff types for typed feedback
HANDOFF_TYPE_PROPOSAL = "proposal"
HANDOFF_TYPE_CRITIQUE = "critique"
HANDOFF_TYPE_APPROVAL = "approval"
HANDOFF_TYPE_FINAL_REQUEST = "final_request"

VALID_HANDOFF_TYPES = frozenset(
    {
        HANDOFF_TYPE_PROPOSAL,
        HANDOFF_TYPE_CRITIQUE,
        HANDOFF_TYPE_APPROVAL,
        HANDOFF_TYPE_FINAL_REQUEST,
    }
)


def normalize_turn_result(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Parse and normalize LLM output into a structured turn result.
    Returns a dict with: status, message, feedback, tool_call, next_agent, thought, done.
    """
    result: dict[str, Any] = {
        "status": TURN_STATUS_CONTINUE,
        "message": "",
        "feedback": [],
        "tool_call": None,
        "next_agent": None,
        "thought": "",
        "done": False,
    }

    thought = raw.get("thought")
    if isinstance(thought, str) and thought.strip():
        result["thought"] = thought.strip()

    message = raw.get("message")
    if isinstance(message, str) and message.strip():
        result["message"] = message.strip()

    feedback = raw.get("feedback")
    if isinstance(feedback, list):
        result["feedback"] = [str(x) for x in feedback if x]
    elif isinstance(feedback, str) and feedback.strip():
        result["feedback"] = [feedback.strip()]

    tool_name = raw.get("tool")
    arguments = raw.get("arguments", {})
    if isinstance(tool_name, str) and tool_name.strip():
        result["tool_call"] = {
            "tool": tool_name.strip(),
            "arguments": arguments if isinstance(arguments, dict) else {},
        }

    next_agent = raw.get("next_agent")
    if isinstance(next_agent, str) and next_agent.strip():
        result["next_agent"] = next_agent.strip()

    status = raw.get("status")
    if isinstance(status, str) and status in VALID_TURN_STATUSES:
        result["status"] = status

    done = raw.get("done")
    if isinstance(done, bool):
        result["done"] = done
    elif result["status"] in (TURN_STATUS_APPROVED, TURN_STATUS_FINAL):
        result["done"] = True

    return result


def build_handoff_record(
    *,
    from_agent: str,
    to_agent: str,
    handoff_type: str,
    content: str,
    output: str,
    summary: str,
    tool_result: Any,
    round_number: int,
    required_changes: list[str] | None = None,
    accepted_constraints: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build a typed handoff record for the next agent.
    """
    record: dict[str, Any] = {
        "fromAgent": from_agent,
        "toAgent": to_agent,
        "handoffType": (
            handoff_type
            if handoff_type in VALID_HANDOFF_TYPES
            else HANDOFF_TYPE_PROPOSAL
        ),
        "content": content,
        "output": output,
        "summary": summary,
        "toolResult": tool_result,
        "round": round_number,
    }
    if required_changes is not None:
        record["requiredChanges"] = required_changes
    if accepted_constraints is not None:
        record["acceptedConstraints"] = accepted_constraints
    return record


def infer_handoff_type(
    agent_role: str,
    status: str,
    has_critique: bool,
) -> str:
    """
    Infer handoff_type from agent context when not explicitly provided.
    """
    role_lower = (agent_role or "").lower()
    if "analyst" in role_lower or "critic" in role_lower or "review" in role_lower:
        if status == TURN_STATUS_APPROVED:
            return HANDOFF_TYPE_APPROVAL
        if has_critique:
            return HANDOFF_TYPE_CRITIQUE
    if "summar" in role_lower or "writer" in role_lower:
        return HANDOFF_TYPE_FINAL_REQUEST
    return HANDOFF_TYPE_PROPOSAL
