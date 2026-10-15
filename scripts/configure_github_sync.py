"""Put locally authorized collector credentials in Actions Secrets, without logging values."""
import argparse, base64, json, os, subprocess
import requests
from dotenv import load_dotenv
from nacl.public import PublicKey, SealedBox

parser=argparse.ArgumentParser()
parser.add_argument('--dispatch',action='store_true')
args=parser.parse_args()
load_dotenv('.env',encoding='utf-8-sig')
credential=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\npath=VietCodeBug/AiVietlot.git\n\n',capture_output=True,text=True,check=True)
values=dict(line.split('=',1) for line in credential.stdout.splitlines() if '=' in line)
token=values.get('password')
if not token:raise SystemExit('No existing GitHub credential is available')
client=requests.Session()
client.headers.update({'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
root='https://api.github.com/repos/VietCodeBug/AiVietlot'
key_response=client.get(root+'/actions/secrets/public-key',timeout=30)
if not key_response.ok:raise SystemExit('Cannot access Actions public key: HTTP '+str(key_response.status_code))
key=key_response.json()
for name in ('SUPABASE_URL','SUPABASE_SECRET_KEY'):
    value=os.environ.get(name,'').strip()
    if not value:raise SystemExit('Missing '+name+' in local environment')
    encrypted=SealedBox(PublicKey(base64.b64decode(key['key']))).encrypt(value.encode())
    result=client.put(root+'/actions/secrets/'+name,json={'key_id':key['key_id'],'encrypted_value':base64.b64encode(encrypted).decode()},timeout=30)
    if result.status_code not in (201,204):raise SystemExit('Cannot save '+name+': HTTP '+str(result.status_code))
    print(name+': configured as encrypted Actions Secret')
if args.dispatch:
    result=client.post(root+'/actions/workflows/sync.yml/dispatches',json={'ref':'main'},timeout=30)
    if result.status_code!=204:raise SystemExit('Cannot dispatch sync workflow: HTTP '+str(result.status_code))
    print(json.dumps({'workflow_dispatched':True,'repository':'VietCodeBug/AiVietlot'}))
