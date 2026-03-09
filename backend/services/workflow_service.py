"""Workflow execution: parse code, validate, build agents, run runner, emit events."""

import uuid
from typing import Any

from agent import Agent

from agent_parser import extract_agent_configs
from events import emit_agent_event, emit_event, log_to_client
from llm import get_llm_client
from runtime import WorkflowRunner
from tools import (
    class_name_to_output_pattern,
    get_session_settings,
    initialize_workflow_session,
    set_workflow_run_id,
    set_workflow_session_id,
    write_session_code,
)

from workflow_state import register_cancel_event, unregister_cancel_event


async def run_workflow(
    session_id: str,
    code: str,
) -> dict[str, Any]:
    """
    Run a workflow for the given session and code.
    Returns a result dict: {"status": "ok", "sessionId", "runId"} or
    {"status": "error", "message": "..."}.
    Caller must clear/set cancel_requested as needed; this function does not touch it.
    """
    await log_to_client("Setting up workflow...")

    from tools import read_workflow_snapshot

    snapshot = read_workflow_snapshot(session_id)
    if snapshot is None:
        return {"status": "error", "message": "Session not found."}

    agent_configs = extract_agent_configs(code)
    if not agent_configs:
        await log_to_client(
            "Error: Failed to parse agent parameters from the submitted script."
        )
        return {
            "status": "error",
            "message": (
                "Could not extract any class-based Agent definitions "
                "(class X(Agent): ... variable = X(task=..., input=...))."
            ),
        }

    variable_to_name = {
        config["variable"]: config["name"] for config in agent_configs
    }
    variable_to_config = {
        config["variable"]: config for config in agent_configs
    }

    for config in agent_configs:
        input_source_variable = config.get("inputSourceVariable")
        if input_source_variable is None:
            continue
        if input_source_variable not in variable_to_config:
            await log_to_client(
                "An agent input referenced an undefined upstream agent output."
            )
            return {
                "status": "error",
                "message": (
                    f"Agent '{config['variable']}' references undefined "
                    f"input source '{input_source_variable}.output'."
                ),
            }

    connections: dict[str, str] = {}
    for config in agent_configs:
        input_source_variable = config.get("inputSourceVariable")
        if input_source_variable is None:
            continue
        source_agent_name = variable_to_name.get(str(input_source_variable))
        target_agent_name = str(config["name"])
        if source_agent_name is None:
            continue
        if source_agent_name in connections:
            await log_to_client(
                "Multiple agents cannot consume the same output in this MVP."
            )
            return {
                "status": "error",
                "message": (
                    f"Output from '{source_agent_name}' is connected to "
                    "multiple agents. This MVP supports a single "
                    "downstream per output."
                ),
            }
        connections[source_agent_name] = target_agent_name

    start_agent_name = (
        next(
            (config["name"] for config in agent_configs if config.get("start")),
            None,
        )
        or agent_configs[0]["name"]
    )

    session_settings = get_session_settings(session_id)
    llm_interface = get_llm_client(settings=session_settings)
    agents = [
        Agent(
            name=str(config["name"]),
            task=str(config["task"]),
            role=str(config.get("role") or ""),
            output_file=class_name_to_output_pattern(config["className"]),
            input_source=(
                variable_to_name.get(str(config["inputSourceVariable"]))
                if config.get("inputSourceVariable") is not None
                else None
            ),
            llm=llm_interface,
            tools=config.get("tools"),
        )
        for config in agent_configs
    ]

    agent_order = [config["name"] for config in agent_configs]
    max_rounds = max((c.get("max_rounds", 8) for c in agent_configs), default=8)
    run_id = uuid.uuid4().hex[:6]
    set_workflow_session_id(session_id)
    set_workflow_run_id(run_id)
    agent_output_files = {
        c["name"]: class_name_to_output_pattern(c["className"])
        for c in agent_configs
    }
    initialize_workflow_session(
        session_id,
        agent_order,
        run_id=run_id,
        agent_output_files=agent_output_files,
    )
    write_session_code(code, session_id)

    for agent in agents:
        agent.add_to_memory("Agent instantiated from submitted script.")
        await emit_agent_event(
            agent_name=agent.name,
            event_type="state",
            message=f"Instantiated agent '{agent.name}' with task '{agent.task}'.",
            state="waiting_for_turn",
            round_number=0,
        )

    await emit_event(
        event_type="workflow_started",
        message=f"Workflow {session_id}-{run_id} started.",
        state="running",
        agent_order=agent_order,
        session_id=session_id,
        run_id=run_id,
    )

    cancel_ev = register_cancel_event(session_id)
    try:
        runner = WorkflowRunner(
            agents=agents,
            start_agent_name=start_agent_name,
            max_rounds=max_rounds,
            connections=connections,
        )
        await runner.run(cancel_event=cancel_ev)
        return {
            "status": "ok",
            "message": f"Workflow finished for {len(agents)} agent(s).",
            "sessionId": session_id,
            "runId": run_id,
        }
    finally:
        unregister_cancel_event(session_id)
        set_workflow_session_id(None)
        set_workflow_run_id(None)
