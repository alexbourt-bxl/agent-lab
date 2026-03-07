import json
from pathlib import Path
import time
from typing import Any

from agent import Agent


DEBUG_LOG_PATH = Path(__file__).resolve().parents[1] / "debug-ecf5ab.log"


def _debug_log(hypothesis_id: str, message: str, data: dict[str, object]) -> None:
    payload = {
        "sessionId": "ecf5ab",
        "runId": "pre-fix",
        "hypothesisId": hypothesis_id,
        "location": "backend/runtime.py",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with DEBUG_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(payload) + "\n")


class WorkflowRunner:
    def __init__(
        self,
        agents: list[Agent],
        start_agent_name: str | None = None,
        max_rounds: int = 5,
        connections: dict[str, str] | None = None,
    ) -> None:
        self.agents = (
            {
                agent.name: agent
                for agent in agents
            }
        )
        self.agent_order = (
            [
                agent.name
                for agent in agents
            ]
        )
        self.start_agent_name = start_agent_name or self.agent_order[0]
        self.max_rounds = max_rounds
        self.connections = connections or {}

    def _format_elapsed(self, seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)

        return f"{m}:{s:02d}"

    async def run(self, model: str | None = None) -> None:
        import time

        from main import emit_agent_event, emit_event
        from tools import get_workflow_run_id, get_workflow_session_id
        from workflow_state import cancel_requested

        def _workflow_prefix() -> str:
            sid = get_workflow_session_id()
            rid = get_workflow_run_id()
            if sid and rid:
                return f"Workflow {sid}-{rid} "
            return "Workflow "

        if not self.agent_order:
            return

        workflow_start = time.perf_counter()

        await self._emit_initial_states()

        current_agent_name = self._resolve_start_agent_name()

        for round_number in range(1, self.max_rounds + 1):
            if cancel_requested.is_set():
                elapsed = time.perf_counter() - workflow_start

                await emit_event(
                    event_type="system",
                    message=f"{_workflow_prefix()}stopped by user ({self._format_elapsed(elapsed)}).",
                    state="stopped",
                    round_number=round_number - 1,
                )
                break

            current_agent = self.agents[current_agent_name]
            turn_result = await current_agent.execute_turn(
                model=model,
                round_number=round_number,
                max_rounds=self.max_rounds,
                available_agents=self.agent_order,
            )

            if turn_result["done"]:
                from main import emit_agent_output

                await emit_agent_output(current_agent.name, current_agent.output)
                await emit_agent_event(
                    agent_name=current_agent.name,
                    event_type="state",
                    state="done",
                    message=f"{current_agent.name} completed the workflow.",
                    round_number=round_number,
                )
                await emit_event(
                    event_type="workflow_result",
                    message=current_agent.output,
                    state="done",
                    round_number=round_number,
                )
                await emit_event(
                    event_type="system",
                    message="Workflow completed.",
                    state="done",
                    round_number=round_number,
                )
                break

            next_agent_name = self._select_next_agent_name(
                current_agent_name=current_agent_name,
                requested_next_agent=turn_result["next_agent"],
            )

            if next_agent_name is None:
                elapsed = time.perf_counter() - workflow_start

                await emit_event(
                    event_type="system",
                    message=f"{_workflow_prefix()}stopped because no next agent was available ({self._format_elapsed(elapsed)}).",
                    state="done",
                    round_number=round_number,
                )
                break

            if next_agent_name != current_agent_name:
                from main import emit_agent_output

                handoff_record = self._build_handoff_record(
                    source_agent_name=current_agent.name,
                    target_agent_name=next_agent_name,
                    turn_result=turn_result,
                    round_number=round_number,
                )
                if current_agent.output:
                    await emit_agent_output(current_agent.name, current_agent.output)
                next_agent = self.agents[next_agent_name]
                next_agent.receive_handoff(handoff_record)

                await emit_agent_event(
                    agent_name=current_agent.name,
                    event_type="state",
                    state="waiting_for_peer",
                    message=f"Waiting for {next_agent_name}.",
                    round_number=round_number,
                )
                await emit_agent_event(
                    agent_name=next_agent_name,
                    event_type="handoff",
                    state="waiting_for_turn",
                    message=self._format_handoff_event_message(handoff_record),
                    round_number=round_number,
                )

            current_agent_name = next_agent_name
        else:
            elapsed = time.perf_counter() - workflow_start

            await emit_event(
                event_type="system",
                message=f"{_workflow_prefix()}stopped after reaching the max round limit ({self._format_elapsed(elapsed)}).",
                state="done",
                round_number=self.max_rounds,
            )

    async def _emit_initial_states(self) -> None:
        from main import emit_agent_event

        for agent_name in self.agent_order:
            await emit_agent_event(
                agent_name=agent_name,
                event_type="state",
                state="waiting_for_turn",
                message=f"{agent_name} is waiting for a turn.",
                round_number=0,
            )

    def _resolve_start_agent_name(self) -> str:
        if self.start_agent_name in self.agents:
            return self.start_agent_name

        return self.agent_order[0]

    def _select_next_agent_name(
        self,
        current_agent_name: str,
        requested_next_agent: str | None,
    ) -> str | None:
        connected_agent_name = self.connections.get(current_agent_name)
        if connected_agent_name is not None:
            if connected_agent_name in self.agents:
                return connected_agent_name

            return None

        if requested_next_agent in self.agents:
            return requested_next_agent

        if len(self.agent_order) == 1:
            return current_agent_name

        current_index = self.agent_order.index(current_agent_name)
        next_index = (current_index + 1) % len(self.agent_order)
        return self.agent_order[next_index]

    def _build_handoff_record(
        self,
        source_agent_name: str,
        target_agent_name: str,
        turn_result: dict[str, Any],
        round_number: int,
    ) -> dict[str, Any]:
        thought = str(turn_result.get("thought", ""))
        tool_result = turn_result.get("tool_result")

        return {
            "fromAgent": source_agent_name,
            "toAgent": target_agent_name,
            "summary": thought,
            "toolResult": tool_result,
            "output": self.agents[source_agent_name].output,
            "round": round_number,
        }

    def _format_handoff_event_message(self, handoff_record: dict[str, Any]) -> str:
        from_agent = str(handoff_record.get("fromAgent", "Unknown"))
        summary = str(handoff_record.get("summary", ""))
        tool_result = handoff_record.get("toolResult")

        if isinstance(tool_result, str) and tool_result != "":
            return (
                f"Received handoff from {from_agent}: "
                f"{summary} | Tool result: {tool_result}"
            )

        return f"Received handoff from {from_agent}: {summary}"
