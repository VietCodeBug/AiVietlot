"""Create a disposable confirmed Auth account without sending email; delete in finally."""
import json, os, secrets, subprocess, sys, uuid
from pathlib import Path
import requests
from dotenv import load_dotenv
load_dotenv('.env',encoding='utf-8-sig')
url=os.environ['SUPABASE_URL']
headers={'apikey':os.environ['SUPABASE_SECRET_KEY'],'Authorization':'Bearer '+os.environ['SUPABASE_SECRET_KEY']}
email='qa-research-'+uuid.uuid4().hex+'@example.invalid'
password=secrets.token_urlsafe(30)
response=requests.post(url+'/auth/v1/admin/users',headers=headers,json={'email':email,'password':password,'email_confirm':True,'user_metadata':{'test_only':True}},timeout=30)
response.raise_for_status()
user=response.json()['id']
try:
    env=dict(os.environ,RESEARCH_QA_EMAIL=email,RESEARCH_QA_PASSWORD=password)
    result=subprocess.run(['node','scripts/qa-research.mjs',*(sys.argv[1:])],cwd=Path('web'),env=env,check=False)
finally:
    cleanup=requests.delete(url+'/auth/v1/admin/users/'+user,headers=headers,timeout=30)
    cleanup.raise_for_status()
    remaining=requests.get(url+'/rest/v1/research_predictions',headers=headers,params={'select':'id','user_id':'eq.'+user},timeout=30)
    remaining.raise_for_status()
    assert remaining.json()==[], 'Disposable research records were not cleaned up'
    print(json.dumps({'disposable_auth_user_deleted':True,'owned_test_tickets_cascaded':True}))
sys.exit(result.returncode)
