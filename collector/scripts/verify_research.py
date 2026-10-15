"""Live PostgreSQL research probes; ALL synthetic users/draws/records roll back."""
import json
from pathlib import Path
import sys
import uuid

import psycopg
from psycopg.types.json import Jsonb
from dotenv import load_dotenv
from migrate import ROOT, connection_options

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv(ROOT / ".env", encoding="utf-8-sig")
checks=[]
connection=psycopg.connect(**connection_options())

def role(name="postgres",user=None):
    connection.execute("reset role")
    connection.execute("select set_config('request.jwt.claims',%s,true)",(json.dumps({"sub":str(user),"role":name}) if user else "{}",))
    connection.execute("select set_config('request.jwt.claim.sub',%s,true)",(str(user) if user else "",))
    if name!="postgres":connection.execute("set local role "+name)

def rejected(query,params=()):
    try:
        with connection.transaction():connection.execute(query,params).fetchall()
    except psycopg.Error:return
    raise AssertionError("A forbidden research operation unexpectedly succeeded")

register="""select to_jsonb(r) from public.register_research_tickets(%s,%s,'manual',
    'rollback-verification-v1','{"test_only":true}'::jsonb,'test-seed',%s,%s,%s) r"""

try:
    initial=connection.execute("select count(*),max(draw_id) from public.mega645_draws").fetchone()
    target=connection.execute("select public.get_research_target()").fetchone()[0]
    target_id=target["target_draw_id"]
    connection.execute("""update public.research_targets set planned_date=greatest(planned_date,
        (clock_timestamp() at time zone 'Asia/Ho_Chi_Minh')::date+1),
        cutoff_at=clock_timestamp()+interval '2 days' where target_draw_id=%s""",(target_id,))
    planned=connection.execute("select planned_date from public.research_targets where target_draw_id=%s",(target_id,)).fetchone()[0]
    first=max(1,target_id-30);last=target_id-1
    fingerprint=connection.execute("select public.research_input_hash(%s,%s)",(first,last)).fetchone()[0]
    users=[uuid.uuid4(),uuid.uuid4()]
    for user in users:
        connection.execute("insert into auth.users(id,aud,role,email,raw_user_meta_data) values(%s,'authenticated','authenticated',%s,%s)",
            (user,f"rollback-research-{user}@example.invalid",Jsonb({"test_only":True})))
    role("anon")
    rejected("select * from public.research_predictions")
    rejected(register,(target_id,Jsonb([{"numbers":[1,2,3,4,5,6]}]),first,last,fingerprint))
    checks.append("anonymous_cannot_read_or_register_private_tickets")
    role("authenticated",users[0])
    params=(target_id,Jsonb([{"numbers":[1,2,3,4,5,6],"purchased":False}]),first,last,fingerprint)
    entry=connection.execute(register,params).fetchone()[0]
    replay=connection.execute(register,params).fetchone()[0]
    assert replay["id"]==entry["id"] and replay["baseline_numbers"]==entry["baseline_numbers"]
    assert entry["numbers"]==[1,2,3,4,5,6] and len(set(entry["baseline_numbers"]))==6
    assert entry["input_hash"]==fingerprint
    checks.append("server_registration_is_owned_seeded_snapshot_checked_and_idempotent")
    rejected(register,(target_id,Jsonb([{"numbers":[2,3,4,5,6,7]}]),first,last,"0"*64))
    rejected("update public.research_predictions set created_at=clock_timestamp()-interval '1 year' where id=%s returning id",(entry["id"],))
    checks.append("snapshot_tampering_and_direct_api_backdating_are_rejected")
    purchased=connection.execute("select to_jsonb(public.set_research_purchase(%s,true))",(entry["id"],)).fetchone()[0]
    assert purchased["purchased"] and purchased["purchased_at"]
    role("authenticated",users[1])
    assert connection.execute("select count(*) from public.research_predictions").fetchone()[0]==0
    rejected("select public.set_research_purchase(%s,true)",(entry["id"],))
    second=connection.execute(register,(target_id,Jsonb([{"numbers":[7,8,9,10,11,12]}]),first,last,fingerprint)).fetchone()[0]
    checks.append("other_accounts_cannot_read_or_mark_another_users_tickets")
    role()
    rejected("update public.research_predictions set seed='backdated' where id=%s returning id",(entry["id"],))
    connection.execute("update public.research_targets set cutoff_at=clock_timestamp()-interval '1 second' where target_draw_id=%s",(target_id,))
    role("authenticated",users[0])
    rejected("select public.set_research_purchase(%s,false)",(entry["id"],))
    rejected(register,(target_id,Jsonb([{"numbers":[2,3,4,5,6,7]}]),first,last,fingerprint))
    checks.append("database_locks_registration_and_purchase_marking_after_cutoff")
    role()
    connection.execute("update public.research_targets set cutoff_at=clock_timestamp()+interval '2 days' where target_draw_id=%s",(target_id,))
    other_target=target_id+1
    connection.execute("insert into public.research_targets(target_draw_id,planned_date,cutoff_at) values(%s,%s,clock_timestamp()+interval '3 days')",(other_target,planned))
    connection.execute("""insert into public.research_predictions(user_id,target_draw_id,numbers,baseline_numbers,
        algorithm,algorithm_version,config,seed,first_draw_id,last_draw_id,input_count,input_hash)
        values(%s,%s,array[1,2,3,4,5,6],array[1,7,13,19,25,31],'manual','rollback-verification-v1',
        '{"test_only":true}','other-target',%s,%s,%s,%s)""",(users[1],other_target,first,last,last-first+1,fingerprint))
    connection.execute("""insert into public.mega645_draws(draw_id,draw_date,n1,n2,n3,n4,n5,n6,
        source_name,source_url,fetched_at,verification_status)
        values(%s,%s,1,2,3,4,5,6,'synthetic-rollback-only','https://example.invalid/test-only',clock_timestamp(),'secondary')""",(target_id,planned))
    outcomes=connection.execute("select prediction_id,match_count,timing_status from public.research_outcomes where draw_id=%s",(target_id,)).fetchall()
    scores={str(row[0]):row[1] for row in outcomes}
    assert scores[entry["id"]]==6 and scores[second["id"]]==0 and len(outcomes)==2
    assert all(row[2]=="prospective" for row in outcomes)
    assert connection.execute("select count(*) from public.research_outcomes where draw_id=%s",(other_target,)).fetchone()[0]==0
    assert connection.execute("select public.reconcile_research_draw(%s)",(target_id,)).fetchone()[0]==0
    checks.append("draw_insert_automatically_records_hits_and_misses_only_for_the_matching_target")
    checks.append("repeated_reconciliation_never_duplicates_outcomes")
    role("authenticated",users[0])
    assert connection.execute("select count(*) from public.research_outcomes").fetchone()[0]==1
    rejected("select public.set_research_purchase(%s,false)",(entry["id"],))
    rejected("select public.reconcile_research_draw(%s)",(target_id,))
    checks.append("outcomes_stay_private_and_purchase_cannot_change_after_result")
    role()
    connection.execute("update public.mega645_draws set n6=10 where draw_id=%s",(target_id,))
    assert connection.execute("select match_count,revision from public.research_outcomes where prediction_id=%s",(entry["id"],)).fetchone()==(5,2)
    assert connection.execute("select count(*) from public.research_outcome_revisions where prediction_id in (%s,%s)",(entry["id"],second["id"])).fetchone()[0]==2
    assert connection.execute("select public.reconcile_research_draw(%s)",(target_id,)).fetchone()[0]==0
    checks.append("controlled_result_corrections_keep_revision_history_without_overwriting_audit")
    connection.rollback()
    assert connection.execute("select count(*),max(draw_id) from public.mega645_draws").fetchone()==initial
    assert connection.execute("select count(*) from auth.users where id=any(%s)",(users,)).fetchone()[0]==0
    report={"status":"passed","checks":checks,"all_test_changes_rolled_back":True,
        "real_draw_count_unchanged":initial[0],"real_latest_draw_unchanged":initial[1]}
    (ROOT/"artifacts"/"research-database-verification.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
except Exception as exc:
    print(json.dumps({"status":"failed","failure_type":type(exc).__name__,"sqlstate":getattr(exc,"sqlstate",None)}))
    raise
finally:
    connection.rollback();connection.close()
