# Agent Lab

Local AI agent experimentation environment.

## Structure

- `frontend/` – React/Vite UI
- `backend/` – FastAPI agent runtime and API
- `supabase/` – local DB config and migrations
- `docs/` – architecture and persistence notes

## Purpose

Use this repository to prototype, test, and iterate on local AI agent workflows across a separated frontend and backend setup.

## Development

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (for Supabase)
- Node.js and npm (for frontend)
- Python 3.x and pip (for backend)

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
- **Other:** `cd backend && pip install -r requirements.txt && python main.py`

Or from root: `npm run dev:backend` (see root `package.json`).

Backend runs at `http://localhost:8000`.

### 3. Frontend

From repo root:

- `cd frontend && npm install && npm run dev`

Or from root: `npm run dev:frontend`.

Frontend runs at `http://localhost:5173` and talks to the backend via the URL in `frontend/.env` or default `http://localhost:8000` (see `frontend/src/api.ts` and optional `VITE_API_URL`).
