import asyncio
import json
import re
import time
from typing import Any

from llm import get_llm_client

from tool import Tool
from tools import (
    ReadFile,
    WriteFile,
    set_workflow_context,
)
from turn_schema import (
    TURN_STATUS_APPROVED,
    TURN_STATUS_FINAL,
    normalize_turn_result,
)


MAX_TOOL_SUBTURNS = 3


def _default_tools() -> list:
    return [ReadFile(), WriteFile()]


class Agent:
    def __init__(
        self,
        name: str,
        task: str,
        role: str = "",
        input: str | None = None,
        output: str = "",
        output_file: str = "{round}.md",
        input_source: str | None = None,
        llm: Any = None,
        tools: list | None = None,
    ) -> None:
        self.name = name
        self.task = task
        self.role = role
        self.input = input
        self.output = output
        self.output_file = output_file
        self.input_source = input_source
        self.memory: list[str] = []
        self.inbox: list[dict[str, Any]] = []
        self.llm = llm or get_llm_client()
        self.tools: dict[str, Any] = {}
        for tool in tools if tools else _default_tools():
            t = tool() if callable(tool) and not hasattr(tool, "name") else tool
            self.register_tool(t)

    def add_to_memory(self, info: str) -> None:
        self.memory.append(info)

    async def _generate_with_progress(
        self,
        prompt: str,
        model: str | None,
        system: str | None,
        round_number: int,
        cancel_event: asyncio.Event | None,
    ) -> str:
        from events import emit_agent_event

        emit_interval = 0.05
        if hasattr(self.llm, "generate_stream"):
            accumulated: list[str] = []
            last_emit = time.monotonic()
            try:
                async for chunk in self.llm.generate_stream(
                    prompt=prompt,
                    model=model,
                    system=system,
                ):
                    if cancel_event is not None and cancel_event.is_set():
                        raise asyncio.CancelledError()
                    accumulated.append(chunk)
                    now = time.monotonic()
                    if now - last_emit >= emit_interval:
                        text = "".join(accumulated)
                        await emit_agent_event(
                            agent_name=self.name,
                            event_type="thought",
                            state="thinking",
                            message=text,
                            round_number=round_number,
                        )
                        last_emit = now
                return "".join(accumulated)
            except asyncio.CancelledError:
                raise
        if cancel_event is not None:
            gen_task = asyncio.create_task(
                self.llm.generate(
                    prompt=prompt,
                    model=model,
                    system=system,
                ),
            )
            cancel_task = asyncio.create_task(cancel_event.wait())
            done, pending = await asyncio.wait(
                [gen_task, cancel_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_task in done:
                gen_task.cancel()
                try:
                    await gen_task
                except asyncio.CancelledError:
                    pass
                raise asyncio.CancelledError()
            cancel_task.cancel()
            try:
                await cancel_task
            except asyncio.CancelledError:
                pass
            return await gen_task
        return await self.llm.generate(
            prompt=prompt,
            model=model,
            system=system,
        )

    def register_tool(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def receive_handoff(self, handoff_record: dict[str, Any]) -> None:
        self.inbox.append(handoff_record)

    def step(self) -> None:
        raise NotImplementedError("Agent.step() must be implemented by subclasses.")

    async def loop(self, model: str | None = None, max_iterations: int = 5) -> None:
        from runtime import WorkflowRunner

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
        cancel_event: asyncio.Event | None = None,
    ) -> dict[str, Any]:
        from events import emit_agent_event

        self._ingest_handoffs()

        await emit_agent_event(
            agent_name=self.name,
            event_type="state",
            state="working",
            message="Working...",
            round_number=round_number,
        )

        agent_list = available_agents or [self.name]
        tool_result_context: list[str] = []
        last_thought = ""
        last_tool_result: str | None = None
        turn_result: dict[str, Any] = {
            "status": "continue",
            "message": "",
            "feedback": [],
            "tool_call": None,
            "next_agent": None,
            "thought": "",
            "tool_result": None,
            "done": False,
        }

        for sub_turn in range(MAX_TOOL_SUBTURNS):
            prompt = self._build_prompt(
                available_agents=agent_list,
                tool_result_context=tool_result_context,
                search_retries_remaining=MAX_TOOL_SUBTURNS - sub_turn - 1,
                round_number=round_number,
                max_rounds=max_rounds,
            )
            system = self._build_system_prompt()
            await emit_agent_event(
                agent_name=self.name,
                event_type="state",
                state="thinking",
                message="Thinking...",
                round_number=round_number,
            )
            raw_output = await self._generate_with_progress(
                prompt=prompt,
                model=model,
                system=system,
                round_number=round_number,
                cancel_event=cancel_event,
            )
            structured_output = self._extract_structured_output(raw_output)
            turn_result = normalize_turn_result(
                structured_output if structured_output else {"thought": raw_output}
            )
            thought = turn_result["thought"] or self._extract_thought(
                raw_output, structured_output
            )
            last_thought = thought

            self.add_to_memory(f"Round {round_number}: {thought}")
            await emit_agent_event(
                agent_name=self.name,
                event_type="thought",
                state="working",
                message=thought,
                round_number=round_number,
            )

            tool_call = turn_result.get("tool_call")
            if tool_call is None:
                break

            tool_result = await self._execute_tool_call_from_dict(
                tool_call=tool_call,
                round_number=round_number,
            )
            if tool_result is not None:
                last_tool_result = tool_result
                self.add_to_memory(f"Tool result: {tool_result}")
                tool_result_context.append(
                    f"Tool result from {tool_call.get('tool', 'tool')}:\n{tool_result}"
                )
                await emit_agent_event(
                    agent_name=self.name,
                    event_type="tool_result",
                    state="working",
                    message=tool_result,
                    round_number=round_number,
                )

        self.output = self._build_output_value(
            thought=last_thought, tool_result=last_tool_result
        )

        done = turn_result.get("done", False)
        if not done and turn_result.get("status") in (
            TURN_STATUS_APPROVED,
            TURN_STATUS_FINAL,
        ):
            done = True

        return {
            "done": done,
            "next_agent": turn_result.get("next_agent"),
            "thought": last_thought,
            "tool_result": last_tool_result,
            "status": turn_result.get("status", "continue"),
            "message": turn_result.get("message", ""),
            "feedback": turn_result.get("feedback", []),
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

            self.add_to_memory(self._format_handoff_record(handoff_record))

        self.inbox.clear()

    def _format_handoff_record(self, handoff_record: dict[str, Any]) -> str:
        from_agent = str(handoff_record.get("fromAgent", "Unknown"))
        summary = str(handoff_record.get("summary", ""))
        handoff_type = str(handoff_record.get("handoffType", "proposal"))
        required_changes = handoff_record.get("requiredChanges", [])
        tool_result = handoff_record.get("toolResult")

        parts = [f"Handoff from {from_agent} ({handoff_type}): {summary}"]
        if required_changes:
            parts.append("Required changes: " + "; ".join(required_changes))
        if isinstance(tool_result, str) and tool_result != "":
            parts.append(f"Tool result: {tool_result}")

        return " | ".join(parts)

    def _build_system_prompt(self) -> str:
        """Build stable system instructions: identity, contract, tool rules, non-hallucination."""
        parts = [
            f"You are {self.name}.",
            "",
        ]
        if self.role:
            parts.extend(
                [
                    f"Role: {self.role}",
                    "",
                ]
            )
        parts.extend(
            [
                "Output contract: Respond with a JSON block inside ```json fences. "
                "Include thought, status, and optionally tool, arguments, next_agent, done.",
                "Valid status: continue, revise, approved, final.",
                "",
                "Tool-calling: Request tools explicitly via tool and arguments when needed. "
                "Do not assume tool results; wait for the backend to return them.",
                "",
                "Non-hallucination: Do not invent external facts. "
                "If you need current information, use the web_search_tool. "
                "Use only evidence from tools or handoffs.",
                "",
            ]
        )
        return "\n".join(parts)

    def _build_prompt(
        self,
        available_agents: list[str],
        tool_result_context: list[str] | None = None,
        search_retries_remaining: int = 2,
        round_number: int = 1,
        max_rounds: int = 5,
    ) -> str:
        teammate_names = [name for name in available_agents if name != self.name]
        teammate_summary = ", ".join(teammate_names) if teammate_names else "None"

        parts = [
            "## Workflow state\n",
            f"Round: {round_number} of {max_rounds}\n",
            f"Other agents: {teammate_summary}\n",
            "",
            "## Task and input\n",
            f"Task: {self.task}\n",
            f"Current input: {self.input if self.input else 'None'}\n",
            "",
            "## Handoff context\n",
            f"{self._summarize_memory()}\n",
            "",
            "## Available tools\n",
            f"{self._format_tools_for_prompt()}\n",
            "",
        ]

        if tool_result_context:
            parts.extend(
                [
                    "## Tool results from this turn\n",
                    "Use this evidence. Do not invent. Cite or refer to findings.\n",
                    "",
                ]
            )
            for block in tool_result_context:
                parts.append(block)
                parts.append("\n\n")
            parts.append(
                "Continue from the evidence above. If you need another search with a "
                "different query, request it. Otherwise produce your response.\n"
            )
            if search_retries_remaining <= 0:
                parts.append(
                    "Search retry budget exhausted. Proceed with the evidence you "
                    "have, or state uncertainty clearly.\n"
                )
            parts.append("\n")

        parts.extend(
            [
                "## Workflow policy\n",
                "If your role is to review or critique, identify faults clearly and "
                "hand work back until satisfied. Only the reviewing agent should set "
                "done to true after approval.\n",
                "If the task involves creating a file, use write_file_tool. "
                "Write final deliverable to session folder (e.g. output.md) before "
                "setting done to true.\n",
                "",
                "## Response format\n",
                "Respond with JSON inside ```json fences:\n",
                "```json\n",
                "{\n",
                '  "thought": "Short reasoning.",\n',
                '  "status": "continue",\n',
                '  "tool": "web_search_tool",\n',
                '  "arguments": {"query": "your search query"},\n',
                '  "next_agent": "Analyst",\n',
                '  "done": false\n',
                "}\n",
                "```\n",
                "Omit tool and arguments if no tool needed. "
                "Use next_agent only when another agent should act next.\n",
            ]
        )

        return "".join(parts)

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

    async def _execute_tool_call_from_dict(
        self,
        tool_call: dict[str, Any],
        round_number: int,
    ) -> str | None:
        from events import emit_agent_event

        tool_name = tool_call.get("tool")
        arguments = tool_call.get("arguments", {})

        if not isinstance(tool_name, str):
            return None

        if not isinstance(arguments, dict):
            arguments = {}

        tool = self.tools.get(tool_name)
        if tool is None or tool.handler is None:
            return f"Unknown tool: {tool_name}"

        from tools import TOOL_NAME_TO_DISPLAY

        display_name = TOOL_NAME_TO_DISPLAY.get(tool_name, tool_name)
        await emit_agent_event(
            agent_name=self.name,
            event_type="tool_call",
            state="executing",
            message=f"Using {display_name} tool",
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
