#!/usr/bin/env python3
"""Apply the declared network PoC release through Ansible."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.lab/infra'


def main():
    subprocess.run([sys.executable, str(ROOT / 'kubernetes/render.py'),
                    '--work', str(WORK), '--ca', str(ROOT / '.lab/ca.pem')], check=True)
    subprocess.run([str(ROOT / 'scripts/deploy.sh'), '-e', 'infra_work=' + str(WORK)],
                   cwd=ROOT, check=True, env={**os.environ,
                       'PLATFORM_INVENTORY': str(WORK / 'linux.yml'),
                       'PLATFORM_PLAYBOOK': 'ansible/playbooks/network-orchestrator.yml'})
    print('Declared network PoC release applied. Run lab:network:verify.')


if __name__ == '__main__':
    main()
