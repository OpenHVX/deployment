"""Shared lab adapter boundaries for explicitly owned VyOS VM lifecycle operations."""
import json
import os
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT/'.lab/network'


def topology():
    environment = ROOT / 'environments/lab'
    inventory = yaml.safe_load((environment / 'inventory.yml').read_text())
    hosts = inventory['all']['children']['hyperv']['hosts']
    nodes = [dict(host=host, **yaml.safe_load(
        (environment / 'host_vars' / (host + '.yml')).read_text())['vyos'])
        for host in hosts]
    for node in nodes:
        if node['cpu'] != 2 or node['memoryGiB'] != 2:
            raise ValueError('The current VyOS lifecycle supports only 2 CPUs and 2 GiB; resize requires a maintenance workflow')
    return nodes


def load_declaration():
    path = WORK/'windows-vars.yml'
    if not path.exists():
        raise SystemExit('No VyOS deployment declaration; run lab:network:vyos-up first')
    return yaml.safe_load(path.read_text())


def playbook(name, host=None, extra=None):
    command = [str(ROOT/'lab/scripts/run-platform.sh'), '-e', '@'+str(WORK/'windows-vars.yml')]
    if host:
        command += ['--limit', host]
    if extra:
        command += ['-e', json.dumps(extra)]
    subprocess.run(command, cwd=ROOT, env={**os.environ, 'PLATFORM_PLAYBOOK': 'ansible/playbooks/'+name+'.yml'}, check=True)


def status(host=None):
    folder = WORK/'instances'
    folder.mkdir(parents=True, exist_ok=True)
    playbook('vyos-status', host, {'vyos_status_dir': str(folder)})
    declaration = load_declaration()
    return {key: json.loads((folder/(key+'.json')).read_text())[0]
            for key in declaration['vyos_hosts'] if not host or key == host}


def add_host_argument(parser):
    parser.add_argument('--host', choices=[node['host'] for node in topology()], help='Restrict the operation to one declared host')
