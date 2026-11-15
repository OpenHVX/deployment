#!/usr/bin/env python3
"""Verify owned VyOS guests by public-key SSH, exact version, MAC and cloud-init status."""
import argparse
import ipaddress
import json
from pathlib import Path
import shlex
import subprocess
import time
from vyos_lifecycle import ROOT, WORK, add_host_argument, load_declaration, status, topology

GUEST = '''import json,socket,subprocess
from pathlib import Path
from vyos.version import get_version_data
print(json.dumps({'hostname':socket.gethostname(),'version':get_version_data()['version'],'mac':Path('/sys/class/net/eth0/address').read_text().strip(),'passwordState':subprocess.check_output(['sudo','passwd','-S','vyos'],text=True).split()[1]}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_host_argument(parser)
    parser.add_argument('--timeout', type=int, default=240)
    args = parser.parse_args()
    declaration = load_declaration()
    identities = status(args.host)
    results = {}
    for node in topology():
        if args.host and node['host'] != args.host:
            continue
        identity = identities[node['host']]
        if identity['State'] != 'Running' or not identity.get('VmId') or not identity.get('Managed'):
            raise SystemExit(f"{node['name']} is not an owned running VM")
        ip = str(ipaddress.IPv4Interface(node['management']).ip)
        command = ['ssh', '-T', '-i', str(ROOT/'.lab/infra/id_ed25519'), '-o', 'BatchMode=yes',
                   '-o', 'ConnectTimeout=4', '-o', 'StrictHostKeyChecking=accept-new',
                   '-o', 'HostKeyAlias='+identity['VmId'], '-o', 'UserKnownHostsFile='+str(WORK/'known_hosts'),
                   '-o', 'PasswordAuthentication=no', 'vyos@'+ip,
                   'sudo cloud-init status --wait >/dev/null 2>&1 && python3 -c '+shlex.quote(GUEST)]
        print(f"Waiting for {node['name']} ({ip}, VM {identity['VmId']})...", flush=True)
        deadline = time.monotonic()+args.timeout
        while True:
            try:
                response = subprocess.run(command, capture_output=True, text=True, timeout=15)
                if response.returncode == 0:
                    data = json.loads(response.stdout)
                    if data['hostname'] != node['name'] or data['version'] != declaration['vyos_image_version']:
                        raise RuntimeError('Guest identity/version differs from declaration')
                    if data['mac'].replace(':','').upper() != node['macAddress']:
                        raise RuntimeError(f"Guest MAC mismatch on {node['name']}: {data['mac']}")
                    if data['passwordState'] != 'L':
                        raise RuntimeError(f"Guest password login is not disabled on {node['name']}: state={data['passwordState']}")
                    results[node['host']] = {**identity, 'guest': data, 'ssh': True, 'cloudInit': True}
                    print(f"Verified {node['name']}: {data['version']}, cloud-init complete, password locked.", flush=True)
                    break
                if 'REMOTE HOST IDENTIFICATION HAS CHANGED' in response.stderr:
                    raise RuntimeError('SSH identity changed for the same VM GUID; refusing trust reset')
            except subprocess.TimeoutExpired:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Timed out verifying {node['name']}; inspect console/cloud-init before retrying")
            time.sleep(3)
    (WORK/'verify-result.json').write_text(json.dumps(results, indent=2)+'\n')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError) as error:
        raise SystemExit(f'VyOS verification failed: {error}') from None
