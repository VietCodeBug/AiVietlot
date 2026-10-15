-- Prospective personal research: server timestamps, immutable numbers and private ownership.
begin;

create or replace function public.mega_numbers_valid(a integer[]) returns boolean
language sql immutable strict set search_path=pg_catalog as $$
  select cardinality(a)=6 and array_lower(a,1)=1 and array_position(a,null) is null
    and 1<=a[1] and a[1]<a[2] and a[2]<a[3] and a[3]<a[4]
    and a[4]<a[5] and a[5]<a[6] and a[6]<=45
$$;

create table if not exists public.research_targets (
  target_draw_id integer primary key check(target_draw_id>0),
  planned_date date not null,
  cutoff_at timestamptz not null,
  schedule_status text not null default 'planned' check(schedule_status in ('planned','confirmed')),
  created_at timestamptz not null default clock_timestamp()
);

create table if not exists public.research_predictions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  target_draw_id integer not null references public.research_targets(target_draw_id),
  numbers integer[] not null check(public.mega_numbers_valid(numbers)),
  baseline_numbers integer[] not null check(public.mega_numbers_valid(baseline_numbers)),
  algorithm text not null check(algorithm in ('uniform','frequency','recency','manual')),
  algorithm_version text not null,
  config jsonb not null check(jsonb_typeof(config)='object'),
  seed text not null,
  first_draw_id integer not null check(first_draw_id>0),
  last_draw_id integer not null check(last_draw_id>=first_draw_id and last_draw_id<target_draw_id),
  input_count integer not null check(input_count>0),
  input_hash text not null check(input_hash ~ '^[a-f0-9]{64}$'),
  created_at timestamptz not null default clock_timestamp(),
  purchased boolean not null default false,
  purchased_at timestamptz,
  unique(user_id,target_draw_id,numbers),
  unique(user_id,target_draw_id,baseline_numbers),
  check((purchased and purchased_at is not null) or (not purchased and purchased_at is null))
);
create index if not exists research_predictions_owner_idx on public.research_predictions(user_id,created_at desc);

create table if not exists public.research_outcomes (
  prediction_id uuid primary key references public.research_predictions(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  draw_id integer not null references public.mega645_draws(draw_id),
  draw_date date not null,
  actual_numbers integer[] not null check(public.mega_numbers_valid(actual_numbers)),
  matched_numbers integer[] not null,
  match_count integer not null check(match_count between 0 and 6),
  baseline_matched_numbers integer[] not null,
  baseline_match_count integer not null check(baseline_match_count between 0 and 6),
  timing_status text not null check(timing_status in ('prospective','invalid_timing')),
  result_source_name text not null,
  result_source_url text not null,
  result_verification_status text not null,
  result_hash text not null,
  revision integer not null default 1,
  compared_at timestamptz not null default clock_timestamp()
);

create table if not exists public.research_outcome_revisions (
  id uuid primary key default gen_random_uuid(),
  prediction_id uuid not null references public.research_predictions(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  previous_outcome jsonb not null,
  changed_at timestamptz not null default clock_timestamp()
);

alter table public.research_targets enable row level security;
alter table public.research_predictions enable row level security;
alter table public.research_outcomes enable row level security;
alter table public.research_outcome_revisions enable row level security;
revoke all on public.research_targets, public.research_predictions,
  public.research_outcomes, public.research_outcome_revisions from public,anon,authenticated;
grant select on public.research_targets to anon,authenticated;
grant select on public.research_predictions,public.research_outcomes,public.research_outcome_revisions to authenticated;
grant all on public.research_targets,public.research_predictions,
  public.research_outcomes,public.research_outcome_revisions to service_role;

drop policy if exists research_target_read on public.research_targets;
create policy research_target_read on public.research_targets for select to anon,authenticated using(true);
drop policy if exists research_owner_read on public.research_predictions;
create policy research_owner_read on public.research_predictions for select to authenticated using(auth.uid()=user_id);
drop policy if exists research_outcome_owner_read on public.research_outcomes;
create policy research_outcome_owner_read on public.research_outcomes for select to authenticated using(auth.uid()=user_id);
drop policy if exists research_revision_owner_read on public.research_outcome_revisions;
create policy research_revision_owner_read on public.research_outcome_revisions for select to authenticated using(auth.uid()=user_id);

create or replace function public.get_research_target() returns jsonb
language plpgsql security definer set search_path=pg_catalog,public as $$
declare latest public.mega645_draws%rowtype; target public.research_targets%rowtype; planned date;
begin
  perform pg_advisory_xact_lock(645,0);
  select * into latest from public.mega645_draws order by draw_id desc limit 1;
  if not found then raise exception 'Chưa có dữ liệu kết quả để xác định kỳ tiếp theo'; end if;
  -- A planned calendar is not evidence of a completed draw. Never advance IDs
  -- beyond latest+1 when the previous result has not been collected.
  planned:=latest.draw_date+1;
  while extract(dow from planned) not in (0,3,5) loop planned:=planned+1; end loop;
  insert into public.research_targets(target_draw_id,planned_date,cutoff_at)
    values(latest.draw_id+1,planned,(planned+time '17:45') at time zone 'Asia/Ho_Chi_Minh')
    on conflict(target_draw_id) do nothing;
  select * into target from public.research_targets where target_draw_id=latest.draw_id+1;
  return to_jsonb(target)||jsonb_build_object('latest_draw_id',latest.draw_id,
    'latest_draw_date',latest.draw_date,'server_now',clock_timestamp(),
    'accepting_entries',clock_timestamp()<target.cutoff_at);
end;
$$;
revoke all on function public.get_research_target() from public;
grant execute on function public.get_research_target() to anon,authenticated,service_role;

create or replace function public.research_input_hash(p_first integer,p_last integer) returns text
language sql stable security definer set search_path=pg_catalog,public as $$
  select encode(sha256(convert_to(string_agg(draw_id::text||'|'||draw_date::text||'|'||
    array_to_string(array[n1,n2,n3,n4,n5,n6],','),E'\n' order by draw_id),'UTF8')),'hex')
  from public.mega645_draws where draw_id between p_first and p_last
$$;
revoke all on function public.research_input_hash(integer,integer) from public,anon,authenticated;
grant execute on function public.research_input_hash(integer,integer) to service_role;

create or replace function public.guard_research_prediction() returns trigger
language plpgsql security definer set search_path=pg_catalog,public as $$
declare cutoff timestamptz;
begin
  if (to_jsonb(new)-array['purchased','purchased_at']) is distinct from
     (to_jsonb(old)-array['purchased','purchased_at']) then
    raise exception 'Dãy, kỳ mục tiêu, cấu hình và thời điểm tạo không được sửa';
  end if;
  select cutoff_at into cutoff from public.research_targets where target_draw_id=old.target_draw_id;
  if clock_timestamp()>=cutoff or exists(select 1 from public.mega645_draws where draw_id=old.target_draw_id) then
    raise exception 'Kỳ đã khóa; không thể thay đổi dấu đã mua';
  end if;
  new.purchased_at:=case when new.purchased then coalesce(old.purchased_at,clock_timestamp()) else null end;
  return new;
end;
$$;
drop trigger if exists research_prediction_guard on public.research_predictions;
create trigger research_prediction_guard before update on public.research_predictions
  for each row execute function public.guard_research_prediction();
revoke all on function public.guard_research_prediction() from public,anon,authenticated;

create or replace function public.register_research_tickets(
  p_target_draw_id integer,p_tickets jsonb,p_algorithm text,p_algorithm_version text,
  p_config jsonb,p_seed text,p_first_draw_id integer,p_last_draw_id integer,p_input_hash text
) returns setof public.research_predictions
language plpgsql security definer set search_path=pg_catalog,public,auth as $$
declare owner uuid:=auth.uid(); target jsonb; item jsonb; chosen integer[]; baseline integer[];
  candidate_id uuid; saved public.research_predictions%rowtype; input_count integer; bought boolean;
begin
  if owner is null then raise exception 'Cần đăng nhập để lưu dãy riêng'; end if;
  perform pg_advisory_xact_lock(645,0);
  target:=public.get_research_target();
  if p_target_draw_id<>(target->>'target_draw_id')::integer then raise exception 'Kỳ mục tiêu đã đổi; hãy tải lại'; end if;
  if not (target->>'accepting_entries')::boolean then raise exception 'Kỳ đã khóa hoặc đang chờ collector lấy kết quả mới'; end if;
  if jsonb_typeof(p_tickets) is distinct from 'array' or jsonb_array_length(p_tickets) not between 1 and 50 then
    raise exception 'Mỗi lần lưu từ 1 đến 50 dãy';
  end if;
  if p_algorithm not in ('uniform','frequency','recency','manual') or p_algorithm is null
    or coalesce(length(p_algorithm_version),0) not between 1 and 80
    or coalesce(length(p_seed),0)>200 or p_seed is null
    or jsonb_typeof(p_config) is distinct from 'object' or length(p_config::text)>10000 then
    raise exception 'Cấu hình thuật toán không hợp lệ';
  end if;
  if p_first_draw_id<1 or p_last_draw_id<p_first_draw_id
    or p_last_draw_id>=(target->>'target_draw_id')::integer then raise exception 'Dữ liệu đầu vào phải nằm trước kỳ mục tiêu'; end if;
  select count(*) into input_count from public.mega645_draws where draw_id between p_first_draw_id and p_last_draw_id;
  if input_count<>p_last_draw_id-p_first_draw_id+1 or input_count=0
    or p_input_hash is distinct from public.research_input_hash(p_first_draw_id,p_last_draw_id) then
    raise exception 'Dữ liệu đầu vào đã đổi hoặc hash không khớp; hãy tạo lại dãy';
  end if;
  for item in select value from jsonb_array_elements(p_tickets) loop
    if jsonb_typeof(item->'numbers') is distinct from 'array' then raise exception 'Thiếu sáu số'; end if;
    select array_agg(value::integer order by value::integer) into chosen from jsonb_array_elements_text(item->'numbers');
    if not coalesce(public.mega_numbers_valid(chosen),false) then raise exception 'Dãy phải có sáu số khác nhau trong 1–45'; end if;
    if item ? 'purchased' and jsonb_typeof(item->'purchased')<>'boolean' then raise exception 'Dấu đã mua phải là boolean'; end if;
    bought:=coalesce((item->>'purchased')::boolean,false);
    select * into saved from public.research_predictions where user_id=owner and target_draw_id=p_target_draw_id and numbers=chosen;
    if found then return next saved; continue; end if;
    loop
      candidate_id:=gen_random_uuid();
      select array_agg(number order by number) into baseline from (
        select number from generate_series(1,45) number
        order by sha256(convert_to(candidate_id::text||':'||number::text,'UTF8')) limit 6
      ) sampled;
      exit when not exists(select 1 from public.research_predictions where user_id=owner
        and target_draw_id=p_target_draw_id and baseline_numbers=baseline);
    end loop;
    if clock_timestamp()>=(target->>'cutoff_at')::timestamptz then raise exception 'Đã đến hạn khóa kỳ'; end if;
    insert into public.research_predictions(id,user_id,target_draw_id,numbers,baseline_numbers,algorithm,
      algorithm_version,config,seed,first_draw_id,last_draw_id,input_count,input_hash,purchased,purchased_at)
    values(candidate_id,owner,p_target_draw_id,chosen,baseline,p_algorithm,p_algorithm_version,p_config,p_seed,
      p_first_draw_id,p_last_draw_id,input_count,p_input_hash,bought,case when bought then clock_timestamp() else null end)
    returning * into saved;
    return next saved;
  end loop;
end;
$$;
revoke all on function public.register_research_tickets(integer,jsonb,text,text,jsonb,text,integer,integer,text) from public,anon;
grant execute on function public.register_research_tickets(integer,jsonb,text,text,jsonb,text,integer,integer,text) to authenticated;

create or replace function public.set_research_purchase(p_prediction_id uuid,p_purchased boolean)
returns public.research_predictions language plpgsql security definer set search_path=pg_catalog,public,auth as $$
declare saved public.research_predictions%rowtype;
begin
  if auth.uid() is null or p_purchased is null then raise exception 'Cần đăng nhập và dấu đã mua hợp lệ'; end if;
  perform pg_advisory_xact_lock(645,0);
  select * into saved from public.research_predictions where id=p_prediction_id and user_id=auth.uid() for update;
  if not found then raise exception 'Không tìm thấy dãy thuộc tài khoản này'; end if;
  update public.research_predictions set purchased=p_purchased where id=p_prediction_id returning * into saved;
  return saved;
end;
$$;
revoke all on function public.set_research_purchase(uuid,boolean) from public,anon;
grant execute on function public.set_research_purchase(uuid,boolean) to authenticated;

create or replace function public.reconcile_research_draw(p_draw_id integer) returns integer
language plpgsql security definer set search_path=pg_catalog,public as $$
declare actual public.mega645_draws%rowtype; prediction public.research_predictions%rowtype;
  old_outcome public.research_outcomes%rowtype; matched integer[]; baseline_matched integer[];
  actual_values integer[]; fingerprint text; cutoff timestamptz; evaluated integer:=0;
begin
  perform pg_advisory_xact_lock(645,0);
  select * into actual from public.mega645_draws where draw_id=p_draw_id;
  if not found then return 0; end if;
  actual_values:=array[actual.n1,actual.n2,actual.n3,actual.n4,actual.n5,actual.n6];
  fingerprint:=encode(sha256(convert_to(actual.draw_date::text||'|'||array_to_string(actual_values,','),'UTF8')),'hex');
  for prediction in select * from public.research_predictions where target_draw_id=p_draw_id loop
    select * into old_outcome from public.research_outcomes where prediction_id=prediction.id;
    if found and old_outcome.result_hash=fingerprint then continue; end if;
    if old_outcome.prediction_id is not null then
      insert into public.research_outcome_revisions(prediction_id,user_id,previous_outcome)
        values(prediction.id,prediction.user_id,to_jsonb(old_outcome));
    end if;
    select coalesce(array_agg(n order by n),'{}'::integer[]) into matched
      from unnest(prediction.numbers) n where n=any(actual_values);
    select coalesce(array_agg(n order by n),'{}'::integer[]) into baseline_matched
      from unnest(prediction.baseline_numbers) n where n=any(actual_values);
    select least(cutoff_at,(actual.draw_date+time '17:45') at time zone 'Asia/Ho_Chi_Minh')
      into cutoff from public.research_targets where target_draw_id=p_draw_id;
    insert into public.research_outcomes(prediction_id,user_id,draw_id,draw_date,actual_numbers,
      matched_numbers,match_count,baseline_matched_numbers,baseline_match_count,timing_status,
      result_source_name,result_source_url,result_verification_status,result_hash,revision)
    values(prediction.id,prediction.user_id,p_draw_id,actual.draw_date,actual_values,matched,cardinality(matched),
      baseline_matched,cardinality(baseline_matched),case when prediction.created_at<cutoff
        and (not prediction.purchased or prediction.purchased_at<cutoff) then 'prospective' else 'invalid_timing' end,
      actual.source_name,actual.source_url,actual.verification_status,fingerprint,coalesce(old_outcome.revision,0)+1)
    on conflict(prediction_id) do update set actual_numbers=excluded.actual_numbers,draw_date=excluded.draw_date,
      matched_numbers=excluded.matched_numbers,match_count=excluded.match_count,
      baseline_matched_numbers=excluded.baseline_matched_numbers,baseline_match_count=excluded.baseline_match_count,
      timing_status=excluded.timing_status,result_source_name=excluded.result_source_name,
      result_source_url=excluded.result_source_url,result_verification_status=excluded.result_verification_status,
      result_hash=excluded.result_hash,revision=excluded.revision,compared_at=clock_timestamp();
    evaluated:=evaluated+1;
  end loop;
  return evaluated;
end;
$$;
revoke all on function public.reconcile_research_draw(integer) from public,anon,authenticated;
grant execute on function public.reconcile_research_draw(integer) to service_role;

create or replace function public.research_draw_arrived() returns trigger
language plpgsql security definer set search_path=pg_catalog,public as $$
begin perform public.reconcile_research_draw(new.draw_id); return new; end;
$$;
revoke all on function public.research_draw_arrived() from public,anon,authenticated;
drop trigger if exists research_draw_settlement on public.mega645_draws;
create trigger research_draw_settlement after insert or update of draw_date,n1,n2,n3,n4,n5,n6
  on public.mega645_draws for each row execute function public.research_draw_arrived();

-- Only owned rows pass realtime's SELECT/RLS checks; never publish auth tables.
do $$
declare name text;
begin
  if exists(select 1 from pg_publication where pubname='supabase_realtime') then
    foreach name in array array['research_predictions','research_outcomes'] loop
      if not exists(select 1 from pg_publication_tables where pubname='supabase_realtime' and schemaname='public' and tablename=name) then
        execute format('alter publication supabase_realtime add table public.%I',name);
      end if;
    end loop;
  end if;
end $$;

notify pgrst,'reload schema';
commit;
