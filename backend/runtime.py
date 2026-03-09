import asyncio
import time
from typing import Any

from agent import Agent

from turn_schema import (
    build_handoff_record as build_typed_handoff,
    infer_handoff_type,
    TURN_STATUS_APPROVED,
)


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

    async def run(
        self,
        model: str | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        import time

        from events import emit_agent_event, emit_event
        from tools import get_workflow_run_id, get_workflow_session_id
        from workflow_state import cancel_requested

        stop_event = cancel_event if cancel_event is not None else cancel_requested

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
        rounds_by_agent: dict[str, int] = {name: 0 for name in self.agent_order}
        safety_limit = self.max_rounds * len(self.agent_order) * 2
        total_turns = 0

        while total_turns < safety_limit:
            total_turns += 1
            if stop_event.is_set():
                elapsed = time.perf_counter() - workflow_start
                last_round = rounds_by_agent.get(current_agent_name, 0)

                await emit_event(
                    event_type="system",
                    message=f"{_workflow_prefix()}stopped by user ({self._format_elapsed(elapsed)}).",
                    state="stopped",
                    round_number=last_round,
                )
                break

            agent_round = rounds_by_agent[current_agent_name] + 1
            if agent_round > self.max_rounds:
                elapsed = time.perf_counter() - workflow_start

                await emit_event(
                    event_type="system",
                    message=f"{_workflow_prefix()}stopped after reaching the max round limit ({self._format_elapsed(elapsed)}).",
                    state="done",
                    round_number=self.max_rounds,
                )
                break

            rounds_by_agent[current_agent_name] = agent_round
            current_agent = self.agents[current_agent_name]
            turn_task = asyncio.create_task(
                current_agent.execute_turn(
                    model=model,
                    round_number=agent_round,
                    max_rounds=self.max_rounds,
                    available_agents=self.agent_order,
                    cancel_event=stop_event,
                ),
            )
            cancel_task = asyncio.create_task(stop_event.wait())
            done, pending = await asyncio.wait(
                [turn_task, cancel_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if cancel_task in done:
                turn_task.cancel()
                try:
                    await turn_task
                except asyncio.CancelledError:
                    pass
                elapsed = time.perf_counter() - workflow_start
                last_round = rounds_by_agent.get(current_agent_name, 0)

                await emit_event(
                    event_type="system",
                    message=f"{_workflow_prefix()}stopped by user ({self._format_elapsed(elapsed)}).",
                    state="stopped",
                    round_number=last_round,
                )
                break

            cancel_task.cancel()
            try:
                await cancel_task
            except asyncio.CancelledError:
                pass

            turn_result = await turn_task

            if turn_result["done"]:
                from events import emit_agent_output

                await emit_agent_output(
                    current_agent.name,
                    current_agent.output,
                    round_number=agent_round,
                )
                await emit_agent_event(
                    agent_name=current_agent.name,
                    event_type="state",
                    state="done",
                    message=f"{current_agent.name} completed the workflow.",
                    round_number=agent_round,
                )
                await emit_event(
                    event_type="workflow_result",
                    message=current_agent.output,
                    state="done",
                    round_number=agent_round,
                )
                await emit_event(
                    event_type="system",
                    message="Workflow completed.",
                    state="done",
                    round_number=agent_round,
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
                    round_number=agent_round,
                )
                break

            if next_agent_name != current_agent_name:
                from events import emit_agent_output

                handoff_record = self._build_handoff_record(
                    source_agent_name=current_agent.name,
                    target_agent_name=next_agent_name,
                    turn_result=turn_result,
                    round_number=agent_round,
                )
                if current_agent.output:
                    await emit_agent_output(
                        current_agent.name,
                        current_agent.output,
                        round_number=agent_round,
                    )
                next_agent = self.agents[next_agent_name]
                next_agent.receive_handoff(handoff_record)

                await emit_event(
                    event_type="handoff",
                    message=f"Handoff: {current_agent.name} → {next_agent_name}",
                    state="handoff",
                    round_number=agent_round,
                )
                await emit_agent_event(
                    agent_name=current_agent.name,
                    event_type="state",
                    state="waiting_for_peer",
                    message=f"Waiting for {next_agent_name}.",
                    round_number=agent_round,
                )
                await emit_agent_event(
                    agent_name=next_agent_name,
                    event_type="handoff",
                    state="waiting_for_turn",
                    message=self._format_handoff_event_message(handoff_record),
                    round_number=rounds_by_agent.get(next_agent_name, 0) + 1,
                )

            current_agent_name = next_agent_name

    async def _emit_initial_states(self) -> None:
        from events import emit_agent_event

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
        status = str(turn_result.get("status", "continue"))
        feedback = turn_result.get("feedback") or []
        message = str(turn_result.get("message", ""))
        source_agent = self.agents[source_agent_name]
        output = source_agent.output

        handoff_type = infer_handoff_type(
            agent_role=source_agent.role,
            status=status,
            has_critique=len(feedback) > 0,
        )

        content = message or thought

        return build_typed_handoff(
            from_agent=source_agent_name,
            to_agent=target_agent_name,
            handoff_type=handoff_type,
            content=content,
            output=output,
            summary=thought,
            tool_result=tool_result,
            round_number=round_number,
            required_changes=feedback if feedback else None,
            accepted_constraints=None,
        )

    def _format_handoff_event_message(self, handoff_record: dict[str, Any]) -> str:
        from_agent = str(handoff_record.get("fromAgent", "Unknown"))
        summary = str(handoff_record.get("summary", ""))
        tool_result = handoff_record.get("toolResult")
        required_changes = handoff_record.get("requiredChanges", [])

        parts = [f"Received handoff from {from_agent}: {summary}"]
        if required_changes:
            parts.append("Required changes: " + "; ".join(required_changes))
        if isinstance(tool_result, str) and tool_result != "":
            parts.append(f"Tool result: {tool_result[:200]}...")

        return " | ".join(parts)
