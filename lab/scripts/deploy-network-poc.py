#!/usr/bin/env python3
"""Apply the declared network release inside the shared maintenance procedure."""
import subprocess
import sys
from lab_runtime import ROOT, WORK, ensure_lab_lock, run_playbook


def main():
    ensure_lab_lock()
    subprocess.run([sys.executable, str(ROOT / 'kubernetes/render.py'),
                    '--work', str(WORK), '--ca', str(ROOT / '.lab/ca.pem')], check=True)
    try:
        run_playbook('maintenance', '-e', 'maintenance_action=enter')
        run_playbook('network-orchestrator', '-e', 'deployment_maintenance_verified=true')
        run_playbook('maintenance', '-e', 'maintenance_action=exit')
    except Exception:
        print('Network deployment stopped. The API gate remains closed if installed. '
              'Inspect the failure; rerun after repair or use lab:maintenance:resume.', file=sys.stderr)
        raise
    print('Declared network release applied; public API admission restored.')


if __name__ == '__main__':
    main()
