#!/usr/bin/env python3
"""Deploy the lab in named stages; keep public API admission closed on failure.

The lab adapter supplies paths and credentials. Ansible owns host configuration;
PowerShell owns native Hyper-V operations; Kustomize owns application resources.
Read main() for execution order. No hidden marker selects a release or opens
registration: both choices live in the tracked Kubernetes overlay.
"""
import argparse
from contextlib import contextmanager
import functools
import http.server
import subprocess
import sys
import threading

from lab_runtime import ROOT, WORK, ensure_lab_lock, run_playbook

# Changing the pinned version is not an upgrade procedure: the role refuses an
# existing installation with another version. Plan upgrades separately.
K3S_VERSION = 'v1.34.13+k3s1'
VERIFIED_MAINTENANCE = ('-e', 'deployment_maintenance_verified=true')


def prepare(script):
    print(f'Preparing {script}', flush=True)
    subprocess.run([sys.executable, str(ROOT / 'lab/scripts' / script)], check=True)


@contextmanager
def media_server():
    """Serve public OS media only, and release the port even after Ansible fails."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(WORK / 'artifacts'))
    server = http.server.ThreadingHTTPServer(('192.168.50.1', 8765), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def configure_infrastructure():
    for script in ('prepare-platform-secrets.py', 'prepare-infra.py', 'prepare-agent.py'):
        prepare(script)
    with media_server():
        run_playbook('infra-vms', '-e', '@' + str(WORK / 'windows-vars.yml'), windows=True)
    credentials = ('-e', '@' + str(WORK / 'secrets.yml'))
    run_playbook('k3s', *credentials, '-e', 'k3s_version=' + K3S_VERSION)
    run_playbook('ceph', *credentials)


def deploy_applications():
    subprocess.run([sys.executable, str(ROOT / 'kubernetes/render.py'),
                    '--work', str(WORK), '--ca', str(ROOT / '.lab/ca.pem')], check=True)
    credentials = ('-e', '@' + str(WORK / 'secrets.yml'))
    run_playbook('backend', *VERIFIED_MAINTENANCE)
    run_playbook('catalog')
    run_playbook('agent', *credentials, *VERIFIED_MAINTENANCE, windows=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--infrastructure-only', action='store_true')
    args = parser.parse_args()
    ensure_lab_lock()
    existing_inventory = (WORK / 'linux.yml').exists()
    try:
        # On a resumed installation, close admission BEFORE any host/service
        # changes. A new installation has no Linux inventory or accepted work.
        if existing_inventory:
            run_playbook('maintenance', '-e', 'maintenance_action=enter')
        configure_infrastructure()
        if not args.infrastructure_only:
            # A first installation can inspect remote state only after K3s is
            # available. Resumed installations already entered maintenance above;
            # keep that gate in place instead of repeating the admission window.
            if not existing_inventory:
                run_playbook('maintenance', '-e', 'maintenance_action=enter')
            deploy_applications()
            run_playbook('maintenance', '-e', 'maintenance_action=exit')
        elif existing_inventory:
            # There may be no apps on an infrastructure-only first installation.
            # The exit helper handles that case without inventing a platform.
            run_playbook('maintenance-resume')
    except Exception:
        print('Deployment stopped. Any installed API gate remains CLOSED. '
              'Inspect the failed step, then rerun or use lab:maintenance:resume '
              'after repair. Existing identities/data must be retained.', file=sys.stderr)
        raise
    if args.infrastructure_only:
        print('Infrastructure ready. Build/import and promote images before deploying applications.')
        return
    # Acceptance needs public admission and may create a tenant/echo task. It is
    # deliberately separate from the mutation window and not a health-only test.
    prepare('smoke-api.py')
    print('Platform deployed; API/agent acceptance passed.')


if __name__ == '__main__':
    main()
