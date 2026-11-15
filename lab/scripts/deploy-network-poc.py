#!/usr/bin/env python3
"""Build and roll out only the network PoC controller/gateway in the existing lab."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.lab/infra'


def remote(script, *args):
    return subprocess.run(['ssh', '-i', str(WORK/'id_ed25519'), '-o', 'BatchMode=yes',
                           '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile='+str(WORK/'known_hosts'),
                           'ubuntu@192.168.50.21', 'python3', '-', *args], input=script, text=True, check=True)


def main():
    # Existing commands can finish on agents during a rollout, but deployment policy
    # deliberately requires draining active work before updating the lab.
    remote('''import subprocess
js = "const m=require('mongoose'); (async()=>{await m.connect(process.env.MONGO_URL); const n=await m.connection.collection('tasks').countDocuments({status:{$in:['queued','sent','reconciling']}}); await m.disconnect(); if(n){console.error('Drain unresolved tasks before deployment');process.exit(1)} })().catch(()=>{console.error('Task preflight failed');process.exit(1)})"
subprocess.run(['sudo','k3s','kubectl','-n','openhvx','exec','deployment/controller','--','node','-e',js],check=True)
''')
    tag_file = WORK/'image-tag'
    previous = tag_file.read_text()
    try:
        subprocess.run([sys.executable, str(ROOT/'lab/scripts/prepare-images.py')], check=True)
        tag = tag_file.read_text().strip()
    finally:
        # Other services keep their existing default image version.
        tag_file.write_text(previous)
    subprocess.run([str(ROOT/'platform/deploy.sh'), '-e', 'infra_work='+str(WORK),
                    '-e', 'image_tag='+tag, '-e', '{"image_names":["controller","api-gateway","network-orchestrator"]}'],
                   cwd=ROOT, env={**os.environ, 'PLATFORM_INVENTORY': str(WORK/'linux.yml'),
                                  'PLATFORM_PLAYBOOK': 'platform/ansible/playbooks/images.yml'}, check=True)
    overrides = WORK/'image-overrides.json'
    values = json.loads(overrides.read_text()) if overrides.exists() else {}
    values.update({name: tag for name in ['controller', 'api-gateway', 'network-orchestrator']})
    overrides.write_text(json.dumps(values, indent=2)+'\n')
    (WORK/'network-settings.json').write_text(json.dumps({'pocEnabled': True})+'\n')
    subprocess.run([sys.executable, str(ROOT/'platform/kubernetes/render.py'), '--work', str(WORK), '--ca', str(ROOT/'.lab/ca.pem')], check=True)
    subprocess.run([str(ROOT/'platform/deploy.sh'), '-e', 'infra_work='+str(WORK)], cwd=ROOT,
                   env={**os.environ,'PLATFORM_INVENTORY':str(WORK/'linux.yml'),'PLATFORM_PLAYBOOK':'platform/ansible/playbooks/network-orchestrator.yml'},check=True)
    remote('''import json,subprocess,sys
tag=sys.argv[1]
for name in ['controller','api-gateway']:
    container={'name':name,'image':'openhvx/'+name+':'+tag}
    if name=='controller':container['env']=[{'name':'NETWORK_POC_ENABLED','value':'true'}]
    patch={'spec':{'template':{'spec':{'containers':[container]}}}}
    subprocess.run(['sudo','k3s','kubectl','-n','openhvx','patch','deployment',name,'--type=strategic','--patch-file=/dev/stdin'],input=json.dumps(patch),text=True,check=True)
    subprocess.run(['sudo','k3s','kubectl','-n','openhvx','rollout','status','deployment/'+name,'--timeout=180s'],check=True)
''', tag)
    print('Logical VPC PoC deployed. Run lab:network:verify. VyOS forwarding is a separate milestone.')


if __name__ == '__main__':
    main()
