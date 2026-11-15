#!/usr/bin/env python3
"""Exercise the lab's public API without printing credentials."""
import json
import secrets
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'.lab/infra'
BASE='https://admin-api.192-168-50-20.sslip.io'
context=ssl.create_default_context(cafile=str(ROOT/'.lab/ca.pem'))

def main():
    config=yaml.safe_load((WORK/'secrets.yml').read_text())
    account=WORK/'admin.json'
    if not account.exists():
        account.write_text(json.dumps({'email':'admin@openhvx.lab','password':secrets.token_urlsafe(30)}));account.chmod(0o600)
    creds=json.loads(account.read_text())
    token=''
    def request(method,path,payload=None,headers=None,allow=()):
        h={'Host':'admin-api.openhvx.lab','Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {}),**(headers or {})}
        req=urllib.request.Request(BASE+path,data=json.dumps(payload).encode() if payload is not None else None,method=method,headers=h)
        try:
            with urllib.request.urlopen(req,context=context,timeout=30) as response:return json.load(response)
        except urllib.error.HTTPError as e:
            if e.code in allow:return None
            raise RuntimeError(f'{method} {path}: HTTP {e.code}: '+e.read().decode()[:1200]) from None
    request('POST','/api/v1/admin/auth/register',creds,{'x-api-key':config['REGISTER_API_KEY']},allow=(409,404))
    login=request('POST','/api/v1/admin/auth/login',creds)
    token=login.get('access_token') or login.get('data',{}).get('access_token')
    if not token:raise RuntimeError('Login did not return an access token')
    cli=WORK/'cli-config.json'
    if not cli.exists():
        pat=request('POST','/api/v1/admin/auth/pats',{'label':'deployment-lab-cli','expiresInDays':30})
        cli.write_text(json.dumps({'profile':{'mode':'admin','currentTenant':'lab-smoke'},'endpoints':{'tenant':{'server':'https://api.192-168-50-20.sslip.io'},'admin':{'server':BASE}},'auth':{'adminPat':pat['token'],'insecure':False}},indent=2)+'\n')
        cli.chmod(0o600)
    request('POST','/api/v1/admin/tenants',{'tenantId':'lab-smoke','name':'Lab acceptance'},allow=(409,))
    for _ in range(45):
        agents=request('GET','/api/v1/admin/agents')
        ids={x['id'] for x in agents.get('data',[]) if x.get('status')=='online'}
        if {'lab-hv01','lab-hv02','lab-hv03','storage-controller-1'} <= ids:break
        time.sleep(2)
    else:raise RuntimeError('All expected v2 agents did not become online')
    print('Registered agents:',json.dumps(agents)[:2200])
    images=request('GET','/api/v1/admin/images')
    print('Image catalog:',json.dumps(images)[:1000])
    payload={'tenantId':'lab-smoke','action':'echo','target':{'kind':'vm','agentId':'lab-hv01'},'data':{'message':'protocol-v2-lab-acceptance'}}
    keyfile=WORK/'echo-key'
    if not keyfile.exists():keyfile.write_text(secrets.token_hex(32))
    accepted=request('POST','/api/v1/admin/tasks',payload,{'Idempotency-Key':keyfile.read_text()})
    replay=request('POST','/api/v1/admin/tasks',payload,{'Idempotency-Key':keyfile.read_text()})
    def findtask(value):
        if isinstance(value,dict):
            if value.get('taskId'):return value
            return findtask(value.get('data',{}))
        return {}
    task=findtask(accepted)
    assert task.get('taskId')==findtask(replay).get('taskId'),'Idempotent replay returned a different task'
    for _ in range(60):
        current=request('GET','/api/v1/admin/tasks/'+task['taskId'])
        state=findtask(current)
        if state.get('status') in ['done','error','reconciling']:
            print('Echo task:',json.dumps(current)[:1600])
            assert state['status']=='done','Echo did not complete successfully'
            break
        time.sleep(2)
    else:raise RuntimeError('Echo task did not finish')
    (WORK/'smoke-result.json').write_text(json.dumps({'echoTaskId':task['taskId'],'echo':'done','idempotentReplay':True}))
    print('Public TLS, authentication, gateway/controller trust, task v2, agent result, and replay validated.')
if __name__=='__main__':main()
