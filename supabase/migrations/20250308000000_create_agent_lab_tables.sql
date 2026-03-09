-- Agent Lab: sessions, agent_outputs, agents

create table if not exists public.sessions (
  id uuid primary key default gen_random_uuid(),
  session_id text unique not null,
  workflow_snapshot jsonb not null default '{}',
  workflow_code text default '',
  agent_code jsonb not null default '{}',
  updated_at timestamptz default now()
);

create table if not exists public.agent_outputs (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.sessions(id) on delete cascade,
  agent_name text not null,
  round int not null,
  content text not null default '',
  created_at timestamptz default now(),
  unique(session_id, agent_name, round)
);

create index if not exists agent_outputs_session_id on public.agent_outputs(session_id);
create index if not exists agent_outputs_agent_round on public.agent_outputs(session_id, agent_name, round desc);

create table if not exists public.agents (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  role text default '',
  tools jsonb not null default '[]',
  code text default '',
  created_at timestamptz default now()
);
