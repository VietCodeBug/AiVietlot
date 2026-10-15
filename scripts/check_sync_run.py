import json, sys, requests
run=sys.argv[1] if len(sys.argv)>1 else '38663883094'
base='https://api.github.com/repos/VietCodeBug/AiVietlot/actions/runs/'+run
response=requests.get(base+'/jobs',timeout=25)
response.raise_for_status()
print(json.dumps([{'job':j['name'],'status':j['status'],'conclusion':j['conclusion'],'steps':[{'name':s['name'],'status':s['status'],'conclusion':s['conclusion']} for s in j['steps']]} for j in response.json()['jobs']],indent=2))
