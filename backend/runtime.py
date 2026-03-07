import json
from pathlib import Path
import re
import time
from collections.abc import Callable
from typing import Any

from llm import OllamaInterface
from tools import read_file_tool, set_workflow_context, write_file_tool


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


class Tool:
    def __init__(
        self,
        name: str,
        description: str = "",
        handler: Callable[..., str] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.handler = handler


class Workflow:
    def __init__(
        self,
        agents: list[str],
        start_agent: str | None = None,
        max_rounds: int = 5,
    ) -> None:
        self.agents = agents
        self.start_agent = start_agent
        self.max_rounds = max_rounds

    def run(self) -> None:
        raise NotImplementedError("Workflow.run() is a script-level workflow entry point.")


class Agent:
    def __init__(
        self,
        name: str,
        goal: str,
        role: str = "",
        input: str | None = None,
        output: str = "",
        input_source: str | None = None,
        llm: OllamaInterface | None = None,
    ) -> None:
        self.name = name
        self.goal = goal
        self.role = role
        self.input = input
        self.output = output
        self.input_source = input_source
        self.memory: list[str] = []
        self.inbox: list[dict[str, Any]] = []
        self.llm = llm or OllamaInterface()
        self.tools: dict[str, Tool] = {}
        self.register_tool(
            Tool(
                name="read_file_tool",
                description="Read the contents of a markdown file from the results directory by filename.",
                handler=read_file_tool,
            )
        )
        self.register_tool(
            Tool(
                name="write_file_tool",
                description="Write content to a markdown file in the results directory by filename.",
                handler=write_file_tool,
            )
        )

    def add_to_memory(self, info: str) -> None:
        self.memory.append(info)

    def register_tool(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def receive_handoff(self, handoff_record: dict[str, Any]) -> None:
        self.inbox.append(handoff_record)

    def step(self) -> None:
        raise NotImplementedError("Agent.step() must be implemented by subclasses.")

    async def loop(self, model: str | None = None, max_iterations: int = 5) -> None:
        runner = WorkflowRunner(
            agents=
            [
                self,
            ],
            start_agent_name=self.name,
            max_rounds=max_iterations,
        )
        await runner.run(model=model)

    async def execute_turn(
        self,
        model: str | None = None,
        round_number: int = 1,
        max_rounds: int = 5,
        available_agents: list[str] | None = None,
    ) -> dict[str, Any]:
        from main import emit_agent_event

        self._ingest_handoffs()

        await emit_agent_event(
            agent_name=self.name,
            event_type="state",
            state="thinking",
            message=f"Thinking...",
            round_number=round_number,
        )

        # region agent log
        _debug_log(
            "H5",
            "execute_turn_start",
            {
                "agentName": self.name,
                "roundNumber": round_number,
                "inputSource": self.input_source,
                "hasInput": self.input is not None and self.input != "",
                "memorySize": len(self.memory),
            },
        )
        # endregion
        prompt = self._build_prompt(
            available_agents=available_agents or
            [
                self.name,
            ]
        )
        system = (
            f"You are {self.name}. {self.role}"
            if self.role
            else None
        )
        raw_output = await self.llm.generate(
            prompt=prompt,
            model=model,
            system=system,
        )
        structured_output = self._extract_structured_output(raw_output)
        thought = self._extract_thought(raw_output, structured_output)

        self.add_to_memory(f"Round {round_number}: {thought}")
        await emit_agent_event(
            agent_name=self.name,
            event_type="thought",
            state="thinking",
            message=thought,
            round_number=round_number,
        )

        tool_result = await self._execute_tool_call(
            structured_output=structured_output,
            round_number=round_number,
        )
        if tool_result is not None:
            self.add_to_memory(f"Tool result: {tool_result}")
            await emit_agent_event(
                agent_name=self.name,
                event_type="tool_result",
                state="thinking",
                message=tool_result,
                round_number=round_number,
            )

        self.output = self._build_output_value(thought=thought, tool_result=tool_result)
        # region agent log
        _debug_log(
            "H6",
            "agent_output_built",
            {
                "agentName": self.name,
                "roundNumber": round_number,
                "outputSource": (
                    "tool_result"
                    if isinstance(tool_result, str) and tool_result != ""
                    else "thought"
                ),
                "outputPreview": self.output[:220],
                "toolResultPreview": tool_result[:220] if isinstance(tool_result, str) else None,
                "thoughtPreview": thought[:220],
            },
        )
        # endregion

        return {
            "done": self._should_stop(
                raw_output=raw_output,
                structured_output=structured_output,
            ),
            "next_agent": self._extract_next_agent(structured_output),
            "thought": thought,
            "tool_result": tool_result,
        }

    def _summarize_memory(self) -> str:
        if not self.memory:
            return "No memory recorded yet."

        return " | ".join(self.memory[-5:])

    def _build_output_value(self, thought: str, tool_result: str | None) -> str:
        if isinstance(tool_result, str) and tool_result != "":
            return tool_result

        return thought

    def _format_tools_for_prompt(self) -> str:
        return "\n".join(
            f"- {tool.name}: {tool.description}"
            for tool in self.tools.values()
        )

    def _ingest_handoffs(self) -> None:
        if not self.inbox:
            return

        for handoff_record in self.inbox:
            output_value = handoff_record.get("output")
            if isinstance(output_value, str) and output_value != "":
                self.input = output_value

            # region agent log
            _debug_log(
                "H7",
                "handoff_ingested",
                {
                    "agentName": self.name,
                    "fromAgent": str(handoff_record.get("fromAgent", "")),
                    "summaryPreview": str(handoff_record.get("summary", ""))[:220],
                    "toolResultPreview": (
                        str(handoff_record.get("toolResult", ""))[:220]
                        if handoff_record.get("toolResult") is not None
                        else None
                    ),
                    "outputPreview": str(handoff_record.get("output", ""))[:220],
                    "assignedInputPreview": self.input[:220] if isinstance(self.input, str) else None,
                },
            )
            # endregion
            self.add_to_memory(self._format_handoff_record(handoff_record))

        self.inbox.clear()

    def _format_handoff_record(self, handoff_record: dict[str, Any]) -> str:
        from_agent = str(handoff_record.get("fromAgent", "Unknown"))
        summary = str(handoff_record.get("summary", ""))
        tool_result = handoff_record.get("toolResult")

        if isinstance(tool_result, str) and tool_result != "":
            return (
                f"Handoff from {from_agent}: "
                f"{summary} | Tool result: {tool_result}"
            )

        return f"Handoff from {from_agent}: {summary}"

    def _build_prompt(self, available_agents: list[str]) -> str:
        teammate_names = [name for name in available_agents if name != self.name]
        teammate_summary = ", ".join(teammate_names) if teammate_names else "None"

        return (
            f"Agent name: {self.name}\n"
            f"Goal: {self.goal}\n"
            f"Current input: {self.input if self.input else 'None'}\n"
            f"Current memory summary: {self._summarize_memory()}\n"
            f"Available tools:\n{self._format_tools_for_prompt()}\n"
            f"Other agents in the workflow: {teammate_summary}\n"
            "Decide the next best action for this agent.\n"
            "If your role is to review, critique, or analyze another agent's output, identify faults clearly and hand the work back until you are satisfied.\n"
            "Only set done to true when your own goal is fully satisfied. If another agent still needs to revise work, keep done false.\n"
            "Use the available tools when they help complete the goal.\n"
            "If the goal involves creating a file, use write_file_tool and prefer markdown filenames. Relative filenames are written into the results directory.\n"
            "Always write your final deliverable to the results folder (e.g. output.md, refined_idea.md) before setting done to true, so the output is visible in the UI.\n"
            "Prefer responding with a JSON block inside ```json fences using this shape:\n"
            "```json\n"
            "{\n"
            '  "thought": "Short reasoning about the next step.",\n'
            '  "tool": "write_file_tool",\n'
            '  "arguments": {\n'
            '    "filename": "hello_world.md",\n'
            '    "content": "# Hello\\n\\nHello, world!\\n"\n'
            "  },\n"
            '  "next_agent": "Analyst",\n'
            '  "done": false\n'
            "}\n"
            "```\n"
            "Use next_agent only if another agent should act after you.\n"
            "In multi-agent review workflows, the reviewing agent should usually be the one to set done to true after approval.\n"
            "If no tool is needed, you may omit tool and arguments.\n"
            "If you do not use JSON, include STOP when the goal is complete."
        )

    def _extract_structured_output(self, output: str) -> dict[str, Any] | None:
        match = re.search(r"```json\s*(\{.*?\})\s*```", output, re.DOTALL)
        candidate = match.group(1) if match else output.strip()

        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return None

        if not isinstance(parsed, dict):
            return None

        return parsed

    def _extract_thought(
        self,
        raw_output: str,
        structured_output: dict[str, Any] | None,
    ) -> str:
        if structured_output is None:
            return raw_output.strip()

        thought = structured_output.get("thought")
        if isinstance(thought, str) and thought.strip():
            return thought

        tool_name = structured_output.get("tool")
        if isinstance(tool_name, str):
            return f"Requested tool: {tool_name}"

        return raw_output.strip()

    def _extract_tool_call(
        self,
        structured_output: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if structured_output is None:
            return None

        tool_name = structured_output.get("tool")
        arguments = structured_output.get("arguments", {})

        if not isinstance(tool_name, str):
            return None

        if not isinstance(arguments, dict):
            return None

        return {
            "tool": tool_name,
            "arguments": arguments,
        }

    async def _execute_tool_call(
        self,
        structured_output: dict[str, Any] | None,
        round_number: int,
    ) -> str | None:
        from main import emit_agent_event

        tool_call = self._extract_tool_call(structured_output)
        if tool_call is None:
            return None

        tool_name = tool_call["tool"]
        arguments = tool_call["arguments"]

        tool = self.tools.get(tool_name)
        if tool is None or tool.handler is None:
            return f"Unknown tool: {tool_name}"

        await emit_agent_event(
            agent_name=self.name,
            event_type="tool_call",
            state="working",
            message=f"{tool_name} with arguments {arguments}",
            round_number=round_number,
        )

        try:
            set_workflow_context(agent_name=self.name, round_number=round_number)
            return tool.handler(**arguments)
        except TypeError as error:
            return f"Tool argument error for {tool_name}: {error}"
        except OSError as error:
            return f"Tool execution error for {tool_name}: {error}"

    def _extract_next_agent(
        self,
        structured_output: dict[str, Any] | None,
    ) -> str | None:
        if structured_output is None:
            return None

        next_agent = structured_output.get("next_agent")
        if not isinstance(next_agent, str) or next_agent.strip() == "":
            return None

        return next_agent

    def _should_stop(
        self,
        raw_output: str,
        structured_output: dict[str, Any] | None,
    ) -> bool:
        if structured_output is not None:
            done = structured_output.get("done")
            if isinstance(done, bool):
                return done

        stop_markers = (
            "stop",
            "done",
            "complete",
            "completed",
            "finished",
        )

        lowered_thought = raw_output.lower()
        return any(marker in lowered_thought for marker in stop_markers)


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
