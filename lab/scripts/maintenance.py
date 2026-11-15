#!/usr/bin/env python3
"""Enter maintenance, or reopen the inspected/repaired lab platform.

This does not roll back resources or change identities. Entering closes public
API admission before draining tasks; resuming waits for workload readiness before
removing the gate. A failed entry keeps any installed gate closed.
"""
import argparse
from lab_runtime import ensure_lab_lock, run_playbook


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', choices=('enter', 'resume'), default='resume')
    args = parser.parse_args()
    ensure_lab_lock()
    if args.action == 'enter':
        run_playbook('maintenance', '-e', 'maintenance_action=enter')
    else:
        run_playbook('maintenance-resume')


if __name__ == '__main__':
    main()
