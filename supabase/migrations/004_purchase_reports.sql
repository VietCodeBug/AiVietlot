-- Supplementary self-reported purchases. Never backdate prospective predictions.
begin;
create table if not exists public.research_purchase_reports (
 id uuid primary key default gen_random_uuid(),
 user_id uuid references auth.users(id) on delete cascade,
 claim_email text not null check(claim_email=lower(trim(claim_email))),
 target_draw_id integer check(target_draw_id>0),
 numbers integer[] not null check(public.mega_numbers_valid(numbers)),
 reported_purchase_date date not null,
 recorded_at timestamptz not null default clock_timestamp(),
 note text not null default '' check(length(note)<=2000),
 unique nulls not distinct(claim_email,target_draw_id,numbers)
);
alter table public.research_purchase_reports enable row level security;
revoke all on public.research_purchase_reports from public,anon,authenticated;
grant select on public.research_purchase_reports to authenticated;
grant all on public.research_purchase_reports to service_role;
drop policy if exists purchase_report_owned on public.research_purchase_reports;
create policy purchase_report_owned on public.research_purchase_reports for select to authenticated using(auth.uid()=user_id);

create or replace function public.add_purchase_report(p_target_draw_id integer,p_numbers integer[],p_purchase_date date,p_note text default '')
returns uuid language plpgsql security definer set search_path=pg_catalog,public,auth as $$
declare owner uuid:=auth.uid(); email text; chosen integer[]; target_date date; result uuid;
begin
 if owner is null then raise exception 'Cần đăng nhập'; end if;
 select lower(u.email) into email from auth.users u where u.id=owner and u.email_confirmed_at is not null;
 if email is null then raise exception 'Cần xác nhận email trước khi lưu vé'; end if;
 select array_agg(n order by n) into chosen from unnest(p_numbers) n;
 if not coalesce(public.mega_numbers_valid(chosen),false) then raise exception 'Cần sáu số khác nhau từ 1 đến 45'; end if;
 select draw_date into target_date from public.mega645_draws where draw_id=p_target_draw_id;
 if not found then
   perform public.get_research_target();
   select planned_date into target_date from public.research_targets where target_draw_id=p_target_draw_id
     and target_draw_id=(select max(draw_id)+1 from public.mega645_draws);
 end if;
 if target_date is null then raise exception 'Chọn kỳ đã có kết quả hoặc kỳ sắp tới'; end if;
 if p_purchase_date is null or p_purchase_date>(clock_timestamp() at time zone 'Asia/Ho_Chi_Minh')::date
   or p_purchase_date>target_date then raise exception 'Ngày mua không thể nằm trong tương lai hoặc sau ngày quay'; end if;
 if p_note is null or length(p_note)>2000 then raise exception 'Ghi chú quá dài'; end if;
 insert into public.research_purchase_reports(user_id,claim_email,target_draw_id,numbers,reported_purchase_date,note)
 values(owner,email,p_target_draw_id,chosen,p_purchase_date,p_note)
 on conflict(claim_email,target_draw_id,numbers) do nothing returning id into result;
 if result is null then select id into result from public.research_purchase_reports where claim_email=email and target_draw_id=p_target_draw_id and numbers=chosen; end if;
 return result;
end $$;
revoke all on function public.add_purchase_report(integer,integer[],date,text) from public,anon;
grant execute on function public.add_purchase_report(integer,integer[],date,text) to authenticated;

create or replace function public.get_purchase_reports() returns setof jsonb
language plpgsql security definer set search_path=pg_catalog,public,auth as $$
declare owner uuid:=auth.uid(); email text;
begin
 if owner is null then raise exception 'Cần đăng nhập'; end if;
 select lower(u.email) into email from auth.users u where u.id=owner and u.email_confirmed_at is not null;
 if email is null then raise exception 'Cần xác nhận email'; end if;
 -- Imported chat reports are released only to a verified account with that email.
 update public.research_purchase_reports set user_id=owner where user_id is null and claim_email=email;
 return query select to_jsonb(p)-'claim_email'||jsonb_build_object(
   'draw_date',d.draw_date,'actual_numbers',case when d.draw_id is not null then array[d.n1,d.n2,d.n3,d.n4,d.n5,d.n6] end,
   'matched_numbers',case when d.draw_id is not null then array(select n from unnest(p.numbers) n where n=any(array[d.n1,d.n2,d.n3,d.n4,d.n5,d.n6])) end,
   'source_url',d.source_url)
 from public.research_purchase_reports p left join public.mega645_draws d on d.draw_id=p.target_draw_id
 where p.user_id=owner order by p.recorded_at desc,p.id;
end $$;
revoke all on function public.get_purchase_reports() from public,anon;
grant execute on function public.get_purchase_reports() to authenticated;

-- A one-time unguessable report ID can be handed to its requester when their
-- account/email is not yet known. No report details are readable before claim.
create or replace function public.claim_purchase_report(p_report_id uuid) returns uuid
language plpgsql security definer set search_path=pg_catalog,public,auth as $$
declare owner uuid:=auth.uid(); email text; report public.research_purchase_reports%rowtype;
begin
 if owner is null then raise exception 'Cần đăng nhập trước khi nhận vé'; end if;
 select lower(u.email) into email from auth.users u where u.id=owner and u.email_confirmed_at is not null;
 if email is null then raise exception 'Cần xác nhận email'; end if;
 select * into report from public.research_purchase_reports where id=p_report_id for update;
 if not found then raise exception 'Không tìm thấy mã nhận vé'; end if;
 if report.user_id=owner then return report.id; end if;
 if report.user_id is not null or (report.claim_email<>'' and report.claim_email<>email) then
   raise exception 'Vé đã thuộc tài khoản khác';
 end if;
 update public.research_purchase_reports set user_id=owner,claim_email=email where id=report.id;
 return report.id;
end $$;
revoke all on function public.claim_purchase_report(uuid) from public,anon;
grant execute on function public.claim_purchase_report(uuid) to authenticated;
notify pgrst,'reload schema';
commit;
