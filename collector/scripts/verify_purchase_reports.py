"""Rollback-only probes for supplementary purchases and one-time ownership claims."""
import json,uuid
from pathlib import Path
import psycopg
from dotenv import load_dotenv
from migrate import ROOT,connection_options
load_dotenv(ROOT/'.env',encoding='utf-8-sig')
connection=psycopg.connect(**connection_options())
checks=[]
def role(name='postgres',user=None):
 connection.execute('reset role')
 connection.execute("select set_config('request.jwt.claims',%s,true)",(json.dumps({'sub':str(user),'role':name}) if user else '{}',))
 connection.execute("select set_config('request.jwt.claim.sub',%s,true)",(str(user) if user else '',))
 if name!='postgres':connection.execute('set local role '+name)
def rejected(sql,args=()):
 try:
  with connection.transaction():connection.execute(sql,args).fetchall()
 except psycopg.Error:return
 raise AssertionError('Forbidden operation succeeded')
try:
 latest,date=connection.execute('select draw_id,draw_date from public.mega645_draws order by draw_id desc limit 1').fetchone()
 users=[uuid.uuid4(),uuid.uuid4(),uuid.uuid4()]
 for i,user in enumerate(users):
  connection.execute("insert into auth.users(id,aud,role,email,email_confirmed_at) values(%s,'authenticated','authenticated',%s,case when %s then clock_timestamp() end)",(user,f'purchase-report-{user}@example.invalid',i<2))
 claim=connection.execute("insert into public.research_purchase_reports(claim_email,target_draw_id,numbers,reported_purchase_date,note) values('',%s,array[1,2,3,4,5,6],%s,'rollback test') returning id",(latest,date)).fetchone()[0]
 role('anon');rejected('select * from public.research_purchase_reports');rejected('select public.claim_purchase_report(%s)',(claim,))
 role('authenticated',users[2]);rejected('select public.claim_purchase_report(%s)',(claim,))
 checks.append('anonymous_and_unconfirmed_accounts_cannot_claim_or_read')
 role('authenticated',users[0])
 assert connection.execute('select count(*) from public.research_purchase_reports').fetchone()[0]==0
 assert connection.execute('select public.claim_purchase_report(%s)',(claim,)).fetchone()[0]==claim
 assert connection.execute('select public.claim_purchase_report(%s)',(claim,)).fetchone()[0]==claim
 report=connection.execute('select public.get_purchase_reports()').fetchone()[0]
 assert report['numbers']==[1,2,3,4,5,6] and report['actual_numbers'] and report['reported_purchase_date']==str(date)
 checks.append('one_time_claim_is_owned_idempotent_and_compares_real_result')
 role('authenticated',users[1]);rejected('select public.claim_purchase_report(%s)',(claim,))
 assert connection.execute('select count(*) from public.research_purchase_reports').fetchone()[0]==0
 rejected('update public.research_purchase_reports set recorded_at=recorded_at-interval \'1 day\' returning id')
 rejected("select public.add_purchase_report(%s,array[1,2,3,4,5,6],current_date+10,'')",(latest,))
 rejected("select public.add_purchase_report(%s,array[1,2,3,4,5,5],%s,'')",(latest,date))
 checks.append('other_account_isolation_invalid_numbers_and_future_dates_rejected')
 saved=connection.execute("select public.add_purchase_report(%s,array[6,5,4,3,2,1],%s,'self reported')",(latest,date)).fetchone()[0]
 replay=connection.execute("select public.add_purchase_report(%s,array[1,2,3,4,5,6],%s,'changed note')",(latest,date)).fetchone()[0]
 assert saved==replay
 role();assert connection.execute('select count(*) from public.research_predictions where user_id=any(%s)',(users,)).fetchone()[0]==0
 checks.append('supplementary_reports_never_create_or_backdate_prospective_predictions')
finally:connection.rollback();connection.close()
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/purchase-report-verification.json').write_text(json.dumps({'status':'passed','all_test_changes_rolled_back':True,'checks':checks},indent=2),encoding='utf-8')
print(json.dumps({'status':'passed','all_test_changes_rolled_back':True,'checks':checks},indent=2))
