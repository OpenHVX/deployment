#!/usr/bin/env python3
"""Compose the lab adapter with shared Ansible platform playbooks."""
import argparse
import functools
import http.server
import os
from pathlib import Path
import subprocess
import sys
import threading
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'.lab/infra'

def run(*args,env=None):subprocess.run(args,cwd=ROOT,env=env,check=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--infrastructure-only', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    for script in ['prepare-platform-secrets.py','prepare-infra.py','prepare-agent.py']:
        run(sys.executable,'lab/scripts/'+script)
    class Server(http.server.ThreadingHTTPServer):
        allow_reuse_address=True
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(WORK/'artifacts'))
    server=Server(('192.168.50.1',8765),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        run('./lab/scripts/run-platform.sh','-e','@'+str(WORK/'windows-vars.yml'),env={**os.environ,'PLATFORM_PLAYBOOK':'ansible/playbooks/infra-vms.yml'})
    finally:
        server.shutdown();server.server_close();thread.join()
    def playbook(name,*args):
        run('./scripts/deploy.sh','-e','@'+str(WORK/'secrets.yml'),'-e','infra_work='+str(WORK),*args,env={**os.environ,'PLATFORM_INVENTORY':str(WORK/'linux.yml'),'PLATFORM_PLAYBOOK':'ansible/playbooks/'+name+'.yml'})
    playbook('k3s','-e','k3s_version=v1.34.13+k3s1')
    playbook('ceph')
    if args.infrastructure_only:
        print('Linux infrastructure ready. Build/import and promote images before applying applications.')
        return
    def backend():
        run(sys.executable,'kubernetes/render.py','--work',str(WORK),'--ca',str(ROOT/'.lab/ca.pem'))
        playbook('backend')
    backend()
    playbook('catalog')
    run('./lab/scripts/run-platform.sh','-e','@'+str(WORK/'secrets.yml'),'-e','infra_work='+str(WORK),env={**os.environ,'PLATFORM_PLAYBOOK':'ansible/playbooks/agent.yml'})
    run(sys.executable,'lab/scripts/smoke-api.py')
    print('Lab platform deployed and API/agent acceptance passed. Run lab:platform:storage-test for the full storage lifecycle.')
if __name__=='__main__':main()
