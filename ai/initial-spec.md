PROJECT: Minimal Local AI Agent Laboratory

You are an expert software architect and coding assistant. Your task is to generate **Cursor prompts** that guide the incremental creation of a project described below.

The prompts should be designed so that a developer using Cursor can paste them sequentially and implement the project in **small, safe stages**.

Your output should be a sequence of prompts for Cursor, each focused on one stage of development.

Do NOT generate the full codebase at once.
Instead generate prompts that build the system **gradually and safely**.

The prompts should be concise but precise enough that Cursor can generate correct code.

---

PROJECT OVERVIEW

The project is a **local AI agent experimentation environment** designed primarily for a single developer.

The goal is to build a system that allows fast experimentation with **autonomous AI agents** running on **local LLMs** such as Ollama.

Ultimately the system should allow experimentation toward a long-term goal:

Building autonomous agents capable of finding business ideas, building software, publishing products, and marketing them with minimal human intervention.

However the MVP is much simpler: it is just a minimal **agent lab environment**.

This environment should allow the user to:

* define agents using a restricted Python syntax
* run autonomous agent loops
* observe reasoning and tool calls
* inspect logs and memory
* experiment rapidly with agent behavior

This is NOT meant to be a production automation system.
It is an **experimental sandbox for autonomous agents**.

---

CORE DESIGN PHILOSOPHY

The system should follow these principles:

1. Extremely simple architecture
2. Minimal dependencies
3. Easy to modify and extend
4. Local-first
5. Observable agent behavior
6. Rapid experimentation

Avoid heavy frameworks or unnecessary complexity.

---

TECHNOLOGY STACK

Frontend

* React
* Vite
* TypeScript
* Monaco Editor (for Python editing)

Backend

* Python
* FastAPI
* Async architecture where useful
* Simple SQLite storage

LLM interface

* Local models via Ollama
* Should be easy to extend to other providers

Communication

Frontend communicates with backend via:

* WebSocket for streaming logs
* HTTP for commands

---

PROJECT STRUCTURE

The project should be organized like this:

/agent-lab
/frontend
/backend

Frontend:

React + Vite project.

Backend:

Python FastAPI server.

---

USER EXPERIENCE

The UI should resemble a minimal development environment.

Layout:

Top bar:
Project title

Main layout:

Left panel:
Python editor where the user writes agent definitions

Right panel:
Visualization placeholder (agent graph or structure)

Bottom panel:
Execution logs and agent reasoning

The UI does not need to be pretty for the MVP.

Focus on functionality.

---

USER PROGRAMMING MODEL

The user defines agents using a **restricted Python API**.

Example:

researcher = Agent(
name="researcher",
goal="find profitable SaaS ideas"
)

researcher.loop()

The system should expose a minimal API:

Agent
Tool
Memory

Agents should support:

goal
tools
memory
loop execution

---

AGENT RUNTIME

Agents run a simple autonomous loop:

observe
plan
act
reflect
repeat

Pseudo structure:

while True:
plan using LLM
choose tool
execute tool
store result in memory
reflect

The loop should run until stopped.

---

TOOLS

Agents should be able to call tools.

MVP tools:

filesystem tools

read_file
write_file
list_files

internet tools

simple web request

execution tools

run_command

Agents should not have unrestricted system access.

Tools should be controlled functions.

---

LLM INTERFACE

The backend should include an LLM abstraction.

Example:

llm.generate(prompt)

For the MVP, connect to Ollama using HTTP.

Model name should be configurable.

---

OBSERVABILITY

The system should log:

agent thoughts
tool calls
results
errors

These logs should stream to the frontend.

---

MVP SCOPE

The MVP is intentionally small.

It should support:

editing Python agent code
running the code
starting an agent loop
streaming logs to the UI
one working tool
one LLM call

Nothing more.

---

IMPLEMENTATION STAGES

You must generate Cursor prompts for the following stages.

Stage 1
Create project structure and skeleton.

Stage 2
Create React frontend using Vite.

Stage 3
Add UI layout with placeholder panels.

Stage 4
Integrate Monaco editor.

Stage 5
Create Python backend with FastAPI.

Stage 6
Create WebSocket logging system.

Stage 7
Create minimal LLM interface to Ollama.

Stage 8
Implement basic Agent runtime class.

Stage 9
Implement simple autonomous agent loop.

Stage 10
Create first tool (filesystem write or read).

Stage 11
Connect frontend run button to backend execution.

Stage 12
Display agent logs in the UI.

Stage 13
Test a full loop where the agent thinks and writes logs.

---

DEVELOPMENT CONSTRAINTS

The code should remain simple.

Avoid unnecessary libraries.

Keep runtime logic small and readable.

Prefer clarity over cleverness.

---

OUTPUT FORMAT

Generate a sequence of **Cursor prompts**.

Each prompt should:

describe the task
explain files to create or modify
explain expected behavior

Each prompt should be usable independently in Cursor.

---

IMPORTANT

Do NOT generate the full implementation.

Generate only the **Cursor prompts for each stage**.

---

END OF SPECIFICATION
