#!/usr/bin/env python3
"""Prepare management-only VyOS media. No host changes and no tenant state."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import shutil
import subprocess
import uuid
import yaml
from vyos_lifecycle import topology

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.lab/network'


def bootstrap(node, public_key):
    parts = public_key.split()
    if len(parts) < 2 or parts[0] != 'ssh-ed25519' or not re.fullmatch(r'[A-Za-z0-9+/=]+', parts[1]):
        raise ValueError('Expected an OpenSSH Ed25519 public key')
    address = ipaddress.IPv4Interface(node['management'])
    return {'ssh_authorized_keys': [public_key], 'vyos_config_commands': [
        f"set system host-name '{node['name']}'",
        f"set interfaces ethernet eth0 address '{address}'",
        "set protocols static route 0.0.0.0/0 next-hop '192.168.50.1'",
        "set system name-server '192.168.50.1'",
        "set service ssh disable-password-authentication",
        f"set service ssh listen-address '{address.ip}'",
        "set system login user vyos authentication public-keys openhvx type 'ssh-ed25519'",
        f"set system login user vyos authentication public-keys openhvx key '{parts[1]}'",
        "set system login user vyos authentication encrypted-password '*'",
    ]}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true', help='Print resource declarations without preparing media')
    parser.add_argument('--image-manifest', type=Path)
    args = parser.parse_args()
    if args.plan:
        print(json.dumps({'phase': 'management-bootstrap', 'tenantNetworkingReady': False, 'routers': topology()}, indent=2))
        return
    if not args.image_manifest:
        parser.error('Supply --image-manifest with an exact-version cloud-init VHDX and its verified SHA256. A generic live ISO is insufficient.')
    manifest = json.loads(args.image_manifest.read_text())
    source = Path(manifest['image']).resolve()
    expected = manifest['sha256']
    if not manifest.get('version') or not re.fullmatch(r'[a-f0-9]{64}', expected):
        raise ValueError('An exact image version and SHA256 are required')
    if not source.is_file() or digest(source) != expected:
        raise ValueError('VyOS cloud image absent or checksum mismatch')
    info = json.loads(subprocess.check_output(['qemu-img', 'info', '--output=json', str(source)], text=True))
    size = manifest['systemGiB']
    if type(size) is not int or size < 4 or info['format'] != 'vhdx' or info.get('backing-filename') or info['virtual-size'] > size * 1024**3:
        raise ValueError('Expected a VHDX fitting the declared systemGiB (at least 4)')
    # Existing platform key is private; only its public counterpart enters seeds.
    public_key = (ROOT / '.lab/infra/id_ed25519.pub').read_text().strip()
    WORK.mkdir(parents=True, exist_ok=True)
    deployment_file = WORK / 'deployment-id'
    if not deployment_file.exists():
        deployment_file.write_text(str(uuid.uuid4())+'\n')
    deployment_id = str(uuid.UUID(deployment_file.read_text().strip()))
    public = WORK / 'artifacts'
    public.mkdir(parents=True, exist_ok=True)
    image = public / ('vyos-'+expected+'.vhdx')
    if image.exists() and digest(image) != expected:
        raise ValueError('Staged image differs; do not replace bootstrap media implicitly')
    if not image.exists():
        shutil.copyfile(source, image)
    hosts = {}
    for node in topology():
        user_data = '#cloud-config\n' + yaml.safe_dump(bootstrap(node, public_key))
        meta_data = yaml.safe_dump({'instance-id': node['name'], 'local-hostname': node['name']})
        network_config = yaml.safe_dump({'version': 2, 'ethernets': {'eth0': {'dhcp4': False, 'dhcp6': False}}})
        content_id = hashlib.sha256((user_data+meta_data+network_config).encode()).hexdigest()[:16]
        folder = WORK / 'seeds' / node['name'] / content_id
        folder.mkdir(parents=True, exist_ok=True)
        for filename, content in [('user-data',user_data),('meta-data',meta_data),('network-config',network_config)]:
            path = folder/filename
            if path.exists() and path.read_text() != content:
                raise ValueError('Content-addressed bootstrap source was modified')
            path.write_text(content)
        seed = public / (node['name']+'-'+content_id+'.iso')
        record = folder/'seed-sha256'
        if seed.exists():
            if not record.exists() or record.read_text().strip() != digest(seed):
                raise ValueError('Cached bootstrap ISO checksum mismatch')
        else:
            subprocess.run(['xorriso', '-as', 'mkisofs', '-quiet', '-V', 'cidata', '-J', '-r', '-o', str(seed),
                            str(folder/'user-data'), str(folder/'meta-data'), str(folder/'network-config')], check=True)
            record.write_text(digest(seed)+'\n')
        hosts[node['host']] = {'name': node['name'], 'seed': seed.name, 'seed_sha256': digest(seed), 'mac_address': node['macAddress']}
    (WORK / 'windows-vars.yml').write_text(yaml.safe_dump({
        'vyos_hosts': hosts, 'vyos_deployment_id': deployment_id, 'vyos_image_sha256': expected,
        'vyos_image_filename': image.name,
        'vyos_image_version': manifest['version'], 'vyos_system_gib': size,
        'vyos_media_url': 'http://192.168.50.1:8766',
    }))
    print('Verified management bootstrap media prepared. No VM changed; no tenant routing configured.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(f'VyOS media preparation failed: {error}') from None
