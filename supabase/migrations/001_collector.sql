-- Mega 6/45 collector. Run once in the Supabase SQL editor or via DATABASE_URL.
-- Public probability data is readable; ingestion metadata and every write are private.
begin;

create table if not exists public.mega645_draws (
    draw_id integer primary key check (draw_id > 0),
    draw_date date not null unique,
    n1 integer not null,
    n2 integer not null,
    n3 integer not null,
    n4 integer not null,
    n5 integer not null,
    n6 integer not null,
    source_name text not null check (length(source_name) > 0),
    source_url text not null check (length(source_url) > 0),
    fetched_at timestamptz not null,
    verification_status text not null check (
        verification_status in ('official', 'secondary', 'cross_checked')
    ),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint mega645_numbers_valid check (
        1 <= n1 and n1 < n2 and n2 < n3 and n3 < n4
        and n4 < n5 and n5 < n6 and n6 <= 45
    )
);

create table if not exists public.ingestion_runs (
    id uuid primary key default gen_random_uuid(),
    mode text not null,
    status text not null default 'running',
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    new_rows integer not null default 0 check (new_rows >= 0),
    duplicate_rows integer not null default 0 check (duplicate_rows >= 0),
    error_count integer not null default 0 check (error_count >= 0),
    latest_draw_id integer,
    meta jsonb not null default '{}'::jsonb
);

create table if not exists public.ingestion_issues (
    id uuid primary key default gen_random_uuid(),
    run_id uuid references public.ingestion_runs(id),
    kind text not null,
    message text not null,
    payload jsonb not null default '{}'::jsonb,
    draw_id integer,
    created_at timestamptz not null default now()
);
create index if not exists ingestion_issues_run_idx
    on public.ingestion_issues(run_id, created_at);

-- Cache a batch's result so retries after a lost HTTP response do not count twice.
create table if not exists public.ingestion_batches (
    request_id uuid primary key,
    run_id uuid not null references public.ingestion_runs(id),
    records jsonb not null,
    result jsonb not null,
    created_at timestamptz not null default now()
);

alter table public.mega645_draws enable row level security;
alter table public.ingestion_runs enable row level security;
alter table public.ingestion_issues enable row level security;
alter table public.ingestion_batches enable row level security;

revoke all on public.mega645_draws from public, anon, authenticated;
revoke all on public.ingestion_runs, public.ingestion_issues,
    public.ingestion_batches from public, anon, authenticated;
grant select on public.mega645_draws to anon, authenticated;
grant all on public.mega645_draws, public.ingestion_runs,
    public.ingestion_issues, public.ingestion_batches to service_role;
drop policy if exists mega645_public_read on public.mega645_draws;
create policy mega645_public_read on public.mega645_draws
    for select to anon, authenticated using (true);

create or replace function public.ingest_mega645_batch(
    p_records jsonb,
    p_run_id uuid,
    p_request_id uuid
) returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    item jsonb;
    candidate public.mega645_draws%rowtype;
    existing public.mega645_draws%rowtype;
    cached public.ingestion_batches%rowtype;
    new_count integer := 0;
    duplicate_count integer := 0;
    error_count integer := 0;
    answer jsonb;
begin
    if jsonb_typeof(p_records) is distinct from 'array' then
        raise exception 'p_records must be a JSON array';
    end if;
    if jsonb_array_length(p_records) > 1000 then
        raise exception 'Batch cannot exceed 1000 records';
    end if;
    if p_request_id is null or p_run_id is null then
        raise exception 'A run id and request id are required';
    end if;
    -- All collectors share the lock: an existing fact is never raced or overwritten.
    perform pg_advisory_xact_lock(645, 0);
    select * into cached from public.ingestion_batches where request_id = p_request_id;
    if found then
        if cached.run_id <> p_run_id or cached.records <> p_records then
            raise exception 'Request id was reused with different input';
        end if;
        return cached.result;
    end if;
    if not exists (select 1 from public.ingestion_runs where id = p_run_id) then
        raise exception 'Ingestion run does not exist';
    end if;

    for item in select value from jsonb_array_elements(p_records) loop
        begin
            if jsonb_typeof(item) is distinct from 'object' then
                raise exception 'Record must be a JSON object';
            end if;
            if jsonb_typeof(item->'draw_id') is distinct from 'number'
                or jsonb_typeof(item->'draw_date') is distinct from 'string'
                or jsonb_typeof(item->'n1') is distinct from 'number'
                or jsonb_typeof(item->'n2') is distinct from 'number'
                or jsonb_typeof(item->'n3') is distinct from 'number'
                or jsonb_typeof(item->'n4') is distinct from 'number'
                or jsonb_typeof(item->'n5') is distinct from 'number'
                or jsonb_typeof(item->'n6') is distinct from 'number'
                or jsonb_typeof(item->'source_name') is distinct from 'string'
                or jsonb_typeof(item->'source_url') is distinct from 'string'
                or jsonb_typeof(item->'fetched_at') is distinct from 'string'
                or jsonb_typeof(item->'verification_status') is distinct from 'string' then
                raise exception 'Record fields have invalid JSON types';
            end if;
            if item->>'draw_id' !~ '^[0-9]+$' or item->>'draw_id' is null
                or item->>'draw_date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                or item->>'draw_date' is null then
                raise exception 'Invalid draw id or date';
            end if;
            candidate.draw_id := (item->>'draw_id')::integer;
            candidate.draw_date := (item->>'draw_date')::date;
            candidate.n1 := (item->>'n1')::integer;
            candidate.n2 := (item->>'n2')::integer;
            candidate.n3 := (item->>'n3')::integer;
            candidate.n4 := (item->>'n4')::integer;
            candidate.n5 := (item->>'n5')::integer;
            candidate.n6 := (item->>'n6')::integer;
            if candidate.draw_id <= 0 or candidate.n1 is null
                or candidate.n2 is null or candidate.n3 is null or candidate.n4 is null
                or candidate.n5 is null or candidate.n6 is null
                or not (1 <= candidate.n1 and candidate.n1 < candidate.n2
                    and candidate.n2 < candidate.n3 and candidate.n3 < candidate.n4
                    and candidate.n4 < candidate.n5 and candidate.n5 < candidate.n6
                    and candidate.n6 <= 45) then
                raise exception 'Numbers must be six distinct ascending integers in 1..45';
            end if;
            candidate.source_name := item->>'source_name';
            candidate.source_url := item->>'source_url';
            if item->>'fetched_at' !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' then
                raise exception 'fetched_at must include an ISO timezone';
            end if;
            candidate.fetched_at := (item->>'fetched_at')::timestamptz;
            candidate.verification_status := item->>'verification_status';
            if coalesce(length(trim(candidate.source_name)), 0) = 0
                or coalesce(length(trim(candidate.source_url)), 0) = 0
                or candidate.fetched_at is null
                or candidate.verification_status is null
                or candidate.verification_status not in ('official', 'secondary', 'cross_checked') then
                raise exception 'Source and verification metadata are required';
            end if;

            select * into existing from public.mega645_draws
                where draw_id = candidate.draw_id;
            if found then
                if existing.draw_date = candidate.draw_date
                    and existing.n1 = candidate.n1 and existing.n2 = candidate.n2
                    and existing.n3 = candidate.n3 and existing.n4 = candidate.n4
                    and existing.n5 = candidate.n5 and existing.n6 = candidate.n6 then
                    duplicate_count := duplicate_count + 1;
                else
                    insert into public.ingestion_issues(run_id, kind, message, payload, draw_id)
                    values (p_run_id, 'conflict', 'Existing draw id has different date or numbers',
                        jsonb_build_object('incoming', item, 'existing', to_jsonb(existing)), candidate.draw_id);
                    error_count := error_count + 1;
                end if;
                continue;
            end if;
            select * into existing from public.mega645_draws
                where draw_date = candidate.draw_date;
            if found then
                insert into public.ingestion_issues(run_id, kind, message, payload, draw_id)
                values (p_run_id, 'date_conflict', 'Existing draw date belongs to another draw id',
                    jsonb_build_object('incoming', item, 'existing', to_jsonb(existing)), candidate.draw_id);
                error_count := error_count + 1;
                continue;
            end if;
            insert into public.mega645_draws(draw_id, draw_date, n1, n2, n3, n4, n5, n6,
                source_name, source_url, fetched_at, verification_status)
            values (candidate.draw_id, candidate.draw_date, candidate.n1, candidate.n2,
                candidate.n3, candidate.n4, candidate.n5, candidate.n6,
                candidate.source_name, candidate.source_url, candidate.fetched_at,
                candidate.verification_status);
            new_count := new_count + 1;
        exception when invalid_text_representation or numeric_value_out_of_range
            or datetime_field_overflow or invalid_datetime_format
            or check_violation or not_null_violation or raise_exception then
            insert into public.ingestion_issues(run_id, kind, message, payload, draw_id)
            values (p_run_id, 'invalid', 'Invalid draw record: ' || sqlerrm, item,
                case when item->>'draw_id' ~ '^[0-9]{1,9}$'
                    then (item->>'draw_id')::integer else null end);
            error_count := error_count + 1;
        end;
    end loop;
    answer := jsonb_build_object('new_rows', new_count, 'duplicate_rows', duplicate_count,
        'error_count', error_count);
    insert into public.ingestion_batches(request_id, run_id, records, result)
        values (p_request_id, p_run_id, p_records, answer);
    return answer;
end;
$$;

revoke all on function public.ingest_mega645_batch(jsonb, uuid, uuid)
    from public, anon, authenticated;
grant execute on function public.ingest_mega645_batch(jsonb, uuid, uuid) to service_role;
notify pgrst, 'reload schema';
commit;
