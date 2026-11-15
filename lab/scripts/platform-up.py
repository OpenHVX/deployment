#!/usr/bin/env python3
"""Compose the lab adapter with shared Ansible platform playbooks."""
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
    os.chdir(ROOT)
    for script in ['prepare-platform-secrets.py','prepare-infra.py','prepare-images.py','prepare-agent.py']:
        run(sys.executable,'lab/scripts/'+script)
    class Server(http.server.ThreadingHTTPServer):
        allow_reuse_address=True
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(WORK/'artifacts'))
    server=Server(('192.168.50.1',8765),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        run('./lab/scripts/run-platform.sh','-e','@'+str(WORK/'windows-vars.yml'),env={**os.environ,'PLATFORM_PLAYBOOK':'platform/ansible/playbooks/infra-vms.yml'})
    finally:
        server.shutdown();server.server_close();thread.join()
    def playbook(name,*args):
        run('./platform/deploy.sh','-e','@'+str(WORK/'secrets.yml'),'-e','infra_work='+str(WORK),*args,env={**os.environ,'PLATFORM_INVENTORY':str(WORK/'linux.yml'),'PLATFORM_PLAYBOOK':'platform/ansible/playbooks/'+name+'.yml'})
    playbook('k3s','-e','k3s_version=v1.34.13+k3s1')
    playbook('ceph')
    playbook('images','-e','image_tag='+(WORK/'image-tag').read_text().strip())
    (WORK/'image-overrides.json').unlink(missing_ok=True)
    def backend():
        run(sys.executable,'platform/kubernetes/render.py','--work',str(WORK),'--ca',str(ROOT/'.lab/ca.pem'))
        playbook('backend')
    backend()
    playbook('catalog')
    run('./lab/scripts/run-platform.sh','-e','@'+str(WORK/'secrets.yml'),'-e','infra_work='+str(WORK),env={**os.environ,'PLATFORM_PLAYBOOK':'platform/ansible/playbooks/agent.yml'})
    run(sys.executable,'lab/scripts/smoke-api.py')
    (WORK/'bootstrap-complete').touch(mode=0o600)
    backend()
    print('Lab platform deployed and API/agent acceptance passed. Run lab:platform:storage-test for the full storage lifecycle.')
if __name__=='__main__':main()
