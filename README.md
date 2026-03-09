# Agent Lab

Local AI agent experimentation environment. Define multi-agent workflows in Python, run them against Ollama, and iterate in a React UI with real-time logs.

## Structure

- `frontend/` – React/Vite UI (Monaco editor, workflow tabs, session management)
- `backend/` – FastAPI agent runtime, WebSocket logs, REST API
- `supabase/` – local DB config and migrations
- `docs/` – architecture and persistence notes

## Purpose

Use this repository to prototype, test, and iterate on local AI agent workflows. Agents are defined as Python classes with tasks, roles, and optional tools (e.g. WebSearch). The runtime orchestrates handoffs between agents and streams events to the frontend via WebSocket.

## Development

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (for Supabase)
- [Ollama](https://ollama.com/) (local LLM)
- Node.js and npm (for frontend)
- Python 3.x and pip (for backend)

Optional: [SearXNG](https://docs.searxng.org/) for the WebSearch tool (configure URL in session settings).

### 1. Supabase (local storage)

Session data, agent output, and saved agents are stored in Supabase. Supabase is the canonical source of truth; see [docs/PERSISTENCE.md](docs/PERSISTENCE.md).

1. Install Docker and start it.
2. From repo root: `npx supabase start`
3. `npx supabase status` – copy **API URL** and **service_role** key.
4. Copy `.env.example` to `.env` and set:
   - `SUPABASE_URL` – e.g. `http://127.0.0.1:54321`
   - `SUPABASE_SERVICE_KEY` – the service_role key
5. `npx supabase db reset` – apply migrations

### 2. Backend

From repo root:

- **Windows:** `.\start-backend.ps1`
- **Other:** `./start-backend.sh` or `cd backend && pip install -r requirements.txt && python main.py`

Or: `npm run dev:backend`

Backend runs at `http://localhost:8000`. LLM server URL and model are configurable per session in the Settings page (default: Ollama at `http://localhost:11434`, model `qwen3:4b`).

### 3. Frontend

From repo root:

- `cd frontend && npm install && npm run dev`

Or: `npm run dev:frontend`

Frontend runs at `http://localhost:5173` and talks to the backend via `VITE_API_URL` in `frontend/.env` (default: `http://localhost:8000`).

## Workflow model

Workflows are defined in a combined Python script: agent classes (extending `Agent`) and instantiations with tasks and connections. Example:

- **Researcher** – task, role, tools (e.g. WebSearch), input from Analyst
- **Analyst** – task, role, input from Researcher

Agents hand off to each other; the runtime emits events (state, handoff, output) over WebSocket for real-time logs.
