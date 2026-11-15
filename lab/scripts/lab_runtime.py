"""Small execution helpers shared by the lab entry points.

Keep orchestration in the calling script. This module only supplies the common
process lock and the existing Ansible runner; it does not model infrastructure.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.lab/infra'


def ensure_lab_lock():
    """Protect direct Python invocations as well as nested mise commands."""
    if os.environ.get('OPENHVX_LAB_LOCK_ROOT') != str(ROOT):
        os.execv(str(ROOT / 'scripts/with-lab-lock.sh'),
                 [str(ROOT / 'scripts/with-lab-lock.sh'), sys.executable, *sys.argv])


def run_playbook(name, *extra, windows=False, variables=None):
    """Supply lab paths explicitly; the generic runner never loads lab secrets."""
    command = [str(ROOT / ('lab/scripts/run-platform.sh' if windows else 'scripts/deploy.sh')),
               '-e', json.dumps({'infra_work': str(WORK), **(variables or {})}), *extra]
    env = {**os.environ, 'PLATFORM_PLAYBOOK': f'ansible/playbooks/{name}.yml'}
    if not windows:
        env['PLATFORM_INVENTORY'] = str(WORK / 'linux.yml')
    subprocess.run(command, cwd=ROOT, env=env, check=True)
