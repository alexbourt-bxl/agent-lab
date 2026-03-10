-- Enable Realtime for sessions and agent_outputs tables.
-- Frontend subscribes to postgres_changes to invalidate cache when backend updates.

alter publication supabase_realtime add table public.sessions;
alter publication supabase_realtime add table public.agent_outputs;
