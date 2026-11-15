#!/usr/bin/env python3
"""Power off one K3s VM, verify VIP/API/task recovery, then restore it."""
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import time
import urllib.request
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'.lab/infra'
CA=ssl.create_default_context(cafile=str(ROOT/'.lab/ca.pem'))
BASE='https://admin-api.192-168-50-20.sslip.io'
SSH=['ssh','-i',str(WORK/'id_ed25519'),'-o','UserKnownHostsFile='+str(WORK/'known_hosts'),'-o','ConnectTimeout=3','-o','BatchMode=yes']
def remote(ip,command):return subprocess.run(SSH+['ubuntu@'+ip,command],check=True,text=True,capture_output=True,timeout=30).stdout

def main():
    config=json.loads((WORK/'cli-config.json').read_text())
    token=config['auth']['adminPat']
    operation_key=secrets.token_hex(32)
    def request(path,payload=None):
        req=urllib.request.Request(BASE+path,data=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json','Authorization':'Bearer '+token,'Idempotency-Key':operation_key} if payload is not None else {'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,context=CA,timeout=20 if payload is not None else 3) as r:return json.load(r)
    nodes=[f'192.168.50.{i}' for i in [21,22,23]]
    for _ in range(45):
        try:
            for ip in nodes:remote(ip,'sudo systemctl is-active --quiet k3s')
            break
        except Exception:time.sleep(2)
    else:raise RuntimeError('All three control nodes must be running before the failure test')
    def hasvip(ip):
        return any(a['local']=='192.168.50.20' for iface in json.loads(remote(ip,'ip -j -4 address show eth0')) for a in iface.get('addr_info',[]))
    owner=next(ip for ip in nodes if hasvip(ip))
    number=int(owner.split('.')[-1])-20
    vm=f'openhvx-cp-{number:02d}'
    host=f'lab-hv{number:02d}'
    restore=WORK/'restore-cp.yml'
    restore.write_text('''- hosts: all
  gather_facts: false
  tasks:
    - ansible.windows.win_powershell:
        script: |
          $Ansible.Changed = $false
          $vm = Get-VM -Name '''+vm+'''
          if ($vm.State -eq 'Off') { Start-VM $vm.Name | Out-Null; $Ansible.Changed = $true }
''')
    stop=WORK/'stop-cp.yml'
    stop.write_text('''- hosts: all
  gather_facts: false
  tasks:
    - ansible.windows.win_powershell:
        script: |
          $vm = Get-VM -Name '''+vm+'''
          if ($vm.State -ne 'Off') { Stop-VM -VM $vm -TurnOff -Force }
''')
    request('/api/v1/healthz')
    started=time.monotonic()
    try:
        subprocess.run([str(ROOT/'lab/scripts/run-platform.sh'),'--limit',host],env={**os.environ,'PLATFORM_PLAYBOOK':str(stop)},cwd=ROOT,check=True)
        for _ in range(60):
            try:
                with socket.socket() as probe:
                    probe.settimeout(1)
                    if probe.connect_ex((owner,22)) == 0:raise RuntimeError('VM has not shut down yet')
                replacement=next(ip for ip in nodes if ip!=owner and hasvip(ip))
                request('/api/v1/healthz')
                break
            except Exception:time.sleep(2)
        else:raise RuntimeError('Management VIP/API did not recover')
        elapsed=time.monotonic()-started
        for _ in range(30):
            try:
                result=request('/api/v1/admin/tasks',{'tenantId':'lab-smoke','action':'echo','target':{'kind':'vm','agentId':'lab-hv03'},'data':{'message':'k3s-vm-failover'}})
                break
            except Exception:time.sleep(2)
        else:raise RuntimeError('Task admission did not recover; retries preserved the same operation key')
        task=result.get('data',result)
        for _ in range(60):
            try:state=request('/api/v1/admin/tasks/'+task['taskId']).get('data',{})
            except Exception:
                time.sleep(2);continue
            if state.get('status')=='done':break
            if state.get('status') in ['error','reconciling']:raise RuntimeError('Task failed during control-node loss')
            time.sleep(2)
        else:raise RuntimeError('Task did not complete during control-node loss')
        report={'stoppedVM':vm,'previousVIPOwner':owner,'replacementVIPOwner':replacement,'apiRecoverySeconds':round(elapsed,2),'echoTaskId':task['taskId'],'echo':'done'}
        (WORK/'failover-result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))
    finally:
        subprocess.run([str(ROOT/'lab/scripts/run-platform.sh'),'--limit',host],env={**os.environ,'PLATFORM_PLAYBOOK':str(restore)},cwd=ROOT,check=True)
    for _ in range(60):
        try:
            ready=json.loads(remote(owner,'sudo k3s kubectl get nodes -o json'))
            if len(ready['items'])==3 and all(any(c['type']=='Ready' and c['status']=='True' for c in n['status']['conditions']) for n in ready['items']):
                print('All three K3s nodes restored to Ready.');return
        except Exception:pass
        time.sleep(2)
    raise RuntimeError('Restored VM did not return to Ready')
if __name__=='__main__':main()
