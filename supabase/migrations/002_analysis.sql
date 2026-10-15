-- Completed, reproducible historical simulations for the public dashboard.
begin;
create table if not exists public.analysis_runs (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    algorithm_version text not null,
    config jsonb not null check (jsonb_typeof(config) = 'object'),
    first_draw_id integer not null check (first_draw_id > 0),
    last_draw_id integer not null check (last_draw_id >= first_draw_id),
    metrics jsonb not null check (jsonb_typeof(metrics) = 'object'),
    status text not null default 'succeeded' check (status in ('running', 'succeeded', 'failed'))
);
create index if not exists analysis_runs_latest_idx on public.analysis_runs(created_at desc);
alter table public.analysis_runs enable row level security;
revoke all on public.analysis_runs from public, anon, authenticated;
grant select on public.analysis_runs to anon, authenticated;
grant all on public.analysis_runs to service_role;
drop policy if exists analysis_runs_public_read on public.analysis_runs;
create policy analysis_runs_public_read on public.analysis_runs
    for select to anon, authenticated using (true);
notify pgrst, 'reload schema';
commit;
