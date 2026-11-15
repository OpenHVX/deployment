"""Shared lab adapter boundaries for explicitly owned VyOS VM lifecycle operations."""
import json
import os
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT/'.lab/network'


def topology():
    return [{'host': f'lab-hv{i:02d}', 'name': f'openhvx-vyos-{i:02d}',
             'management': f'192.168.50.{40+i}/24', 'cpu': 2, 'memoryGiB': 2,
             'macAddress': f'00155D4856{i:02X}'}
            for i in range(1, 4)]



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
    subprocess.run(command, cwd=ROOT, env={**os.environ, 'PLATFORM_PLAYBOOK': 'platform/ansible/playbooks/'+name+'.yml'}, check=True)


def status(host=None):
    folder = WORK/'instances'
    folder.mkdir(parents=True, exist_ok=True)
    playbook('vyos-status', host, {'vyos_status_dir': str(folder)})
    declaration = load_declaration()
    return {key: json.loads((folder/(key+'.json')).read_text())[0]
            for key in declaration['vyos_hosts'] if not host or key == host}


def add_host_argument(parser):
    parser.add_argument('--host', choices=['lab-hv01', 'lab-hv02', 'lab-hv03'], help='Restrict the operation to one declared host')
