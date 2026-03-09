#!/usr/bin/env bash
# Agent Lab - Start backend
# Run from project root. Starts the FastAPI server (loads .env automatically).
# Requires: Supabase running (npx supabase start), Python deps (pip install -r backend/requirements.txt)

set -e
cd "$(dirname "$0")/backend"
exec python main.py
