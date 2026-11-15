#!/usr/bin/env python3
"""Lab adapter serving only verified OS media and public-key bootstrap seeds."""
import argparse
import functools
import http.server
import os
from pathlib import Path
import subprocess
import sys
import threading
import ipaddress
import socket
from vyos_lifecycle import add_host_argument, status, topology

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-manifest', type=Path, default=Path(os.environ.get('VYOS_IMAGE_MANIFEST', str(ROOT/'.lab/network/image.json'))))
    add_host_argument(parser)
    args = parser.parse_args()
    if not args.image_manifest.exists() and args.image_manifest == ROOT/'.lab/network/image.json':
        subprocess.run([sys.executable, str(ROOT/'image-builds/vyos/build.py')], check=True)
    subprocess.run([sys.executable, str(ROOT/'lab/scripts/prepare-vyos.py'),
                    '--image-manifest', str(args.image_manifest.resolve())], check=True)
    identities = status(args.host)
    for node in topology():
        if args.host and node['host'] != args.host:
            continue
        if identities[node['host']]['State'] != 'absent' and not identities[node['host']].get('Managed'):
            raise RuntimeError('An existing VM is not owned by this deployment')
        if identities[node['host']]['State'] == 'Running':
            continue
        ip = str(ipaddress.IPv4Interface(node['management']).ip)
        occupied = subprocess.run(['ping', '-c', '1', '-W', '1', ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        try:
            with socket.create_connection((ip, 22), timeout=1):
                occupied = True
        except OSError:
            pass
        if occupied:
            raise RuntimeError(f'Management address {ip} responds while its owned VM is not running; inspect the address conflict')
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT/'.lab/network/artifacts'))
    server = http.server.ThreadingHTTPServer(('192.168.50.1', 8766), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        limit = ['--limit', args.host] if args.host else []
        subprocess.run([str(ROOT/'lab/scripts/run-platform.sh'), '-e', '@'+str(ROOT/'.lab/network/windows-vars.yml'), *limit],
                       cwd=ROOT, env={**os.environ, 'PLATFORM_PLAYBOOK': 'ansible/playbooks/vyos.yml'}, check=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    subprocess.run([sys.executable, str(ROOT/'lab/scripts/verify-vyos.py'), *(['--host', args.host] if args.host else [])], check=True)
    print('Owned VyOS VMs deployed and guest identity/version/cloud-init verified.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'VyOS deployment failed; inspect vyos-status before retrying: {error}') from None
