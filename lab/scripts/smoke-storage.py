#!/usr/bin/env python3
"""Validate catalog -> Ceph clone/iSCSI -> Hyper-V VM -> managed cleanup."""
import argparse
import re
import json
from pathlib import Path
import secrets
import ssl
import time
import urllib.error
import urllib.request
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'.lab/infra'
BASE='https://admin-api.192-168-50-20.sslip.io'
context=ssl.create_default_context(cafile=str(ROOT/'.lab/ca.pem'))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',default='initial',help='Identity of a distinct acceptance scenario; preserve on retries')
    run=parser.parse_args().run
    if not re.fullmatch(r'[a-z0-9-]{1,30}',run):raise SystemExit('Invalid run identity')
    tenant='lab-storage-'+run
    token=''
    def request(method,path,payload=None,headers=None,allow=()):
        req=urllib.request.Request(BASE+path,data=json.dumps(payload).encode() if payload is not None else None,method=method,headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {}),**(headers or {})})
        try:
            with urllib.request.urlopen(req,context=context,timeout=30) as r:return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in allow:return None
            raise RuntimeError(f'{method} {path}: HTTP {e.code}: '+e.read().decode()[:1000]) from None
    login=request('POST','/api/v1/admin/auth/login',json.loads((WORK/'admin.json').read_text()))
    token=login.get('access_token') or login.get('data',{}).get('access_token')
    request('POST','/api/v1/admin/tenants',{'tenantId':tenant,'name':'Storage acceptance','quotas':{'cpu':8,'memoryMB':8192,'storageMB':32768,'vmCount':4}},allow=(409,))
    def operation(stage,action,target,data):
        path=WORK/(run+'-'+stage+'-key')
        if not path.exists():path.write_text(secrets.token_hex(32))
        accepted=request('POST','/api/v1/admin/tasks',{'tenantId':tenant,'action':action,'target':target,'data':data},{'Idempotency-Key':path.read_text()})
        task=accepted.get('data',accepted)
        for _ in range(150):
            result=request('GET','/api/v1/admin/tasks/'+task['taskId']).get('data',{})
            if result.get('status') in ['done','error','reconciling']:
                (WORK/(run+'-'+stage+'-result.json')).write_text(json.dumps(result))
                print(stage,result['taskId'],result['status'],result.get('error',''))
                if result['status']!='done':raise RuntimeError(stage+' requires investigation; operation identity and partial resources preserved')
                return result
            time.sleep(2)
        raise RuntimeError(stage+' did not finish; do not submit a new identity')
    storage={'kind':'storage','agentId':'storage-controller-1'}
    disk=operation('storage-create','storage.create',storage,{'name':'lab-e2e-'+run,'imageId':'ubuntu-24.04','sizeMB':8192})
    diskid=disk['result']['disk']['refId']
    vm=operation('vm-create','vm.create',{'kind':'vm','agentId':'lab-hv01'},{'name':'lab-e2e-'+run,'diskId':diskid,'cpu':2,'ram':'2GB','ha':False})
    details=vm['result']['vm']
    print('Created VM:',json.dumps(details)[:1400])
    guid=details.get('id') or details.get('guid') or details.get('refId')
    if not guid:raise RuntimeError('VM result did not expose an identity; inspect before cleanup')
    operation('vm-delete','vm.delete',{'kind':'vm','agentId':'lab-hv01','refId':guid},{'guid':guid,'forceStop':True})
    operation('storage-delete','storage.delete',{**storage,'refId':diskid},{'refId':diskid})
    (WORK/(run+'-storage-smoke-complete')).write_text('catalog -> storage -> VM -> cleanup validated\n')
    print('Storage and Hyper-V lifecycle validated; acceptance resources removed.')
if __name__=='__main__':main()
