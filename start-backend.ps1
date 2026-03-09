# Agent Lab - Start backend
# Run from project root. Starts the FastAPI server (loads .env automatically).
# Requires: Supabase running (npx supabase start), Python deps (pip install -r backend/requirements.txt)

$ErrorActionPreference = "Stop"
$BackendDir = Join-Path $PSScriptRoot "backend"
Push-Location $BackendDir
try
{
    python main.py
}
finally
{
    Pop-Location
}
