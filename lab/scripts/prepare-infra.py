#!/usr/bin/env python3
"""Prepare Ubuntu media and connection inventories; never modify a host.

Cloud-init seeds describe first boot, not ongoing guest configuration. If the
requested seed differs from an existing one, stop before rewriting any seed or
inventory. Use an explicit guest maintenance/rebuild workflow for that change.
"""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import urllib.request

import yaml
from lab_runtime import ROOT, WORK, ensure_lab_lock

PUBLIC = WORK / 'artifacts'
ENVIRONMENT = ROOT / 'environments/lab'
UBUNTU_URL = 'https://cloud-images.ubuntu.com/noble/20261017/'
UBUNTU_IMAGE = 'noble-server-cloudimg-amd64.img'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def seed_contents(name, address, public_key):
    """Keep the established cloud-init format so existing lab seeds stay valid."""
    user = {
        'hostname': name, 'manage_etc_hosts': True,
        'users': [{'name': 'ubuntu', 'groups': ['sudo'], 'shell': '/bin/bash',
                   'sudo': 'ALL=(ALL) NOPASSWD:ALL', 'ssh_authorized_keys': [public_key]}],
        'ssh_pwauth': False, 'disable_root': True,
    }
    network = {'version': 2, 'ethernets': {'eth0': {
        'match': {'driver': 'hv_netvsc'}, 'set-name': 'eth0', 'dhcp4': False,
        'addresses': [address + '/24'],
        'routes': [{'to': 'default', 'via': '192.168.50.1'}],
        'nameservers': {'addresses': ['192.168.50.1']},
    }}}
    return {
        'user-data': '#cloud-config\n' + yaml.safe_dump(user),
        'meta-data': yaml.safe_dump({'instance-id': name, 'local-hostname': name}),
        'network-config': yaml.safe_dump(network),
    }


def verify_existing_seed(iso, contents):
    """Compare the ISO itself, not just editable files beside the cached image."""
    if not iso.exists():
        return
    with tempfile.TemporaryDirectory(prefix='seed-check-') as tmp:
        extracted = Path(tmp) / 'contents'
        subprocess.run(['xorriso', '-osirrox', 'on', '-indev', str(iso),
                        '-extract', '/', str(extracted)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if {path.name for path in extracted.iterdir()} != set(contents):
            raise ValueError(f'{iso.name}: unexpected bootstrap files; inspect the existing media before proceeding')
        for filename, expected in contents.items():
            source = extracted / filename
            if not source.is_file() or source.read_text() != expected:
                raise ValueError(
                    f'{iso.name}: {filename} differs from the requested bootstrap. '
                    'Existing media and inventories were retained. Inspect the guest; '
                    'use an explicit maintenance/rebuild workflow, not seed regeneration.')


def write_seed(folder, iso, contents):
    folder.mkdir(parents=True, exist_ok=True)
    for filename, content in contents.items():
        (folder / filename).write_text(content)
    if not iso.exists():
        # Never publish a partial ISO: a failed xorriso run must be safe to retry.
        temporary = iso.with_suffix('.iso.partial')
        try:
            subprocess.run(['xorriso', '-as', 'mkisofs', '-quiet', '-V', 'cidata',
                            '-J', '-r', '-o', str(temporary),
                            *[str(folder / name) for name in contents]], check=True)
            temporary.replace(iso)
        finally:
            temporary.unlink(missing_ok=True)


def prepare_base_image():
    sums = urllib.request.urlopen(UBUNTU_URL + 'SHA256SUMS', timeout=60).read().decode()
    expected = next(line.split()[0] for line in sums.splitlines()
                    if line.split()[-1].lstrip('*') == UBUNTU_IMAGE)
    image = WORK / UBUNTU_IMAGE
    if not image.exists():
        temporary = image.with_suffix('.partial')
        urllib.request.urlretrieve(UBUNTU_URL + UBUNTU_IMAGE, temporary)
        if sha256(temporary) != expected:
            raise ValueError('Downloaded Ubuntu image checksum mismatch')
        temporary.replace(image)
    if sha256(image) != expected:
        raise ValueError('Cached Ubuntu image checksum mismatch')
    vhdx = PUBLIC / 'ubuntu.vhdx'
    if not vhdx.exists():
        temporary = vhdx.with_suffix('.vhdx.partial')
        subprocess.run(['qemu-img', 'convert', '-f', 'qcow2', '-O', 'vhdx',
                        str(image), str(temporary)], check=True)
        temporary.replace(vhdx)
    return vhdx


def main():
    ensure_lab_lock()
    PUBLIC.mkdir(parents=True, exist_ok=True)
    key = WORK / 'id_ed25519'
    if not key.exists():
        # Losing this key is a recovery event when guests already exist.
        if (WORK / 'linux.yml').exists():
            raise ValueError('Management key is missing for an existing inventory; restore it from backup')
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
    public_key = key.with_suffix('.pub').read_text().strip()
    inventory = yaml.safe_load((ENVIRONMENT / 'inventory.yml').read_text())
    declarations = {}
    for host in inventory['all']['children']['hyperv']['hosts']:
        declarations[host] = yaml.safe_load(
            (ENVIRONMENT / 'host_vars' / (host + '.yml')).read_text())['infrastructure_vms']

    # Validate every existing ISO before publishing even one changed inventory.
    for machines in declarations.values():
        for vm in machines:
            contents = seed_contents(vm['name'], vm['address'], public_key)
            verify_existing_seed(PUBLIC / (vm['name'] + '.iso'), contents)

    vhdx = prepare_base_image()
    nodes, windows = {}, {}
    for host, machines in declarations.items():
        windows[host] = {'infra_vms': []}
        for vm in machines:
            name = vm['name']
            iso = PUBLIC / (name + '.iso')
            write_seed(WORK / name, iso, seed_contents(name, vm['address'], public_key))
            windows[host]['infra_vms'].append({
                'name': name, 'seed': iso.name, 'seed_sha256': sha256(iso),
                'data_gib': vm['data_gib'], 'system_gib': vm['system_gib'],
            })
            nodes[name] = {'ansible_host': vm['address'], 'infra_role': vm['role']}
    connections = {'all': {
        'vars': {
            'ansible_user': 'ubuntu', 'ansible_become': True,
            'ansible_ssh_private_key_file': str(key),
            'ansible_ssh_common_args': '-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=' + str(WORK / 'known_hosts'),
        },
        'children': {role: {'hosts': {name: values for name, values in nodes.items()
                                    if values['infra_role'] == role}} for role in ('cp', 'ceph')},
    }}
    (WORK / 'linux.yml').write_text(yaml.safe_dump(connections))
    (WORK / 'windows-vars.yml').write_text(yaml.safe_dump({
        'infra_hosts': windows, 'infra_image_sha256': sha256(vhdx),
        'infra_media_url': 'http://192.168.50.1:8765',
    }))
    print('Verified media and inventories prepared; no VM modified.')


if __name__ == '__main__':
    main()
