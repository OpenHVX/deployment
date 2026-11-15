#!/usr/bin/env python3
"""Prepare verified Ubuntu Hyper-V media and a lab infrastructure inventory."""
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.lab/infra'
PUBLIC = WORK / 'artifacts'

def run(*args):
    subprocess.run(args, check=True)

def main():
    PUBLIC.mkdir(parents=True, exist_ok=True)
    key = WORK / 'id_ed25519'
    if not key.exists():
        run('ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key))
    pub = key.with_suffix('.pub').read_text().strip()
    # Verify the downloaded image against Ubuntu's HTTPS checksum catalog.
    base = 'https://cloud-images.ubuntu.com/noble/20261017/'
    name = 'noble-server-cloudimg-amd64.img'
    sums = urllib.request.urlopen(base + 'SHA256SUMS').read().decode()
    digest = next(line.split()[0] for line in sums.splitlines() if line.split()[-1].lstrip('*') == name)
    image = WORK / name
    if not image.exists():
        urllib.request.urlretrieve(base + name, image)
    if hashlib.file_digest(image.open('rb'), 'sha256').hexdigest() != digest:
        raise SystemExit('Ubuntu image checksum mismatch')
    vhdx = PUBLIC / 'ubuntu.vhdx'
    if not vhdx.exists():
        run('qemu-img', 'convert', '-f', 'qcow2', '-O', 'vhdx', str(image), str(vhdx))
    nodes = {}
    windows = {}
    environment = ROOT / 'environments/lab'
    inventory = yaml.safe_load((environment / 'inventory.yml').read_text())
    for host in inventory['all']['children']['hyperv']['hosts']:
        vms = []
        declaration = yaml.safe_load((environment / 'host_vars' / (host + '.yml')).read_text())
        for vm in declaration['infrastructure_vms']:
            role, name, ip = vm['role'], vm['name'], vm['address']
            folder = WORK / name
            folder.mkdir(exist_ok=True)
            user = {'hostname': name, 'manage_etc_hosts': True, 'users': [{'name': 'ubuntu', 'groups': ['sudo'], 'shell': '/bin/bash', 'sudo': 'ALL=(ALL) NOPASSWD:ALL', 'ssh_authorized_keys': [pub]}], 'ssh_pwauth': False, 'disable_root': True}
            (folder / 'user-data').write_text('#cloud-config\n' + yaml.safe_dump(user))
            (folder / 'meta-data').write_text(yaml.safe_dump({'instance-id': name, 'local-hostname': name}))
            (folder / 'network-config').write_text(yaml.safe_dump({'version': 2, 'ethernets': {'eth0': {'match': {'driver': 'hv_netvsc'}, 'set-name': 'eth0', 'dhcp4': False, 'addresses': [ip+'/24'], 'routes': [{'to': 'default', 'via': '192.168.50.1'}], 'nameservers': {'addresses': ['192.168.50.1']}}}}))
            iso = PUBLIC / (name+'.iso')
            if not iso.exists():
                run('xorriso', '-as', 'mkisofs', '-quiet', '-V', 'cidata', '-J', '-r', '-o', str(iso), str(folder/'user-data'), str(folder/'meta-data'), str(folder/'network-config'))
            vms.append({'name': name, 'seed': name+'.iso', 'seed_sha256': hashlib.file_digest(iso.open('rb'), 'sha256').hexdigest(), 'data_gib': vm['data_gib'], 'system_gib': vm['system_gib']})
            nodes[name] = {'ansible_host': ip, 'infra_role': role}
        windows[host] = {'infra_vms': vms}
    inventory = {'all': {'vars': {'ansible_user': 'ubuntu', 'ansible_ssh_private_key_file': str(key), 'ansible_ssh_common_args': '-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile='+str(WORK/'known_hosts'), 'ansible_become': True}, 'children': {role: {'hosts': {k: v for k,v in nodes.items() if v['infra_role']==role}} for role in ['cp','ceph']}}}
    (WORK/'linux.yml').write_text(yaml.safe_dump(inventory))
    (WORK/'windows-vars.yml').write_text(yaml.safe_dump({'infra_hosts': windows, 'infra_image_sha256': hashlib.file_digest(vhdx.open('rb'), 'sha256').hexdigest(), 'infra_media_url': 'http://192.168.50.1:8765'}))
    print('Verified media and inventory prepared; no VM modified.')
if __name__ == '__main__': main()
