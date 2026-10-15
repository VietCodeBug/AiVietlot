import json, os
import requests
from dotenv import load_dotenv
load_dotenv('.env',encoding='utf-8-sig')
r=requests.get(os.environ['SUPABASE_URL']+'/auth/v1/settings',headers={'apikey':os.environ['SUPABASE_SECRET_KEY']},timeout=25)
r.raise_for_status()
d=r.json()
print(json.dumps({k:d.get(k) for k in ('disable_signup','mailer_autoconfirm','external','email')},indent=2))
