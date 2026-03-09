# Agent Lab

Local AI agent experimentation environment.

## Structure

- `frontend/` for UI and client-side experiments
- `backend/` for agent, API, and runtime experiments

## Purpose

Use this repository to prototype, test, and iterate on local AI agent workflows across a separated frontend and backend setup.

## Supabase (local storage)

Session data, agent output, and saved agents are stored in Supabase. Run locally:

1. Install [Docker](https://docs.docker.com/get-docker/) and start it.
2. `npx supabase start`
3. `npx supabase status` – copy `API URL` and `service_role key`
4. Set env vars (or create `.env` from `.env.example`):
   - `SUPABASE_URL` – e.g. `http://127.0.0.1:54321`
   - `SUPABASE_SERVICE_KEY` – the service_role key
5. `npx supabase db reset` – apply migrations
6. Start backend: `.\start-backend.ps1` (or `cd backend && python main.py`)
