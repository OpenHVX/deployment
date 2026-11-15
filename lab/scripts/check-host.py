#!/usr/bin/env python3
"""Read-only workstation diagnostics. Exit nonzero on unmet prerequisites."""
import ipaddress
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

errors = []
def check(ok, message):
    print(f"{'OK' if ok else 'ERREUR'} : {message}")
    if not ok:
        errors.append(message)

def run(*args):
    return subprocess.run(args, text=True, capture_output=True, timeout=30)

check(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'Linux x86-64')
print(platform.platform())
cpu = Path('/proc/cpuinfo').read_text()
print(next((line for line in cpu.splitlines() if line.startswith('model name')), 'CPU inconnu'))
flags = set(next((line.split(':', 1)[1] for line in cpu.splitlines() if line.startswith('flags')), '').split())
check({'vmx', 'ept'} <= flags or {'svm', 'npt'} <= flags, 'VT-x/EPT ou AMD-V/NPT')
check(os.access('/dev/kvm', os.R_OK | os.W_OK), '/dev/kvm accessible par cet utilisateur')
nested = [p for p in (Path('/sys/module/kvm_intel/parameters/nested'), Path('/sys/module/kvm_amd/parameters/nested')) if p.exists()]
check(any(p.read_text().strip().lower() in ('y', '1') for p in nested), 'virtualisation imbriquée activée')
check(shutil.which('virsh') is not None, 'virsh disponible (paquet système libvirt)')
if shutil.which('virsh'):
    result = run('virsh', '-c', 'qemu:///system', 'version')
    check(result.returncode == 0, 'connexion qemu:///system autorisée')
    if result.returncode:
        print(result.stderr.strip())

memory = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))) // 1024
storage_path = Path('/var/lib/libvirt/images')
if not storage_path.exists():
    storage_path = storage_path.parent
free_gib = shutil.disk_usage(storage_path).free // (1024 ** 3)
requested_memory = int(os.environ.get('LAB_MEMORY_MIB', '32768'))
requested_cpu = int(os.environ.get('LAB_VCPU', '8'))
requested_disk = int(os.environ.get('LAB_DISK_GIB', '200'))
host_count = int(os.environ.get('LAB_HOST_COUNT', '3'))
cidr = os.environ.get('LAB_MANAGEMENT_CIDR', '192.168.50.0/24')
# Inspect the actual saved plan when called by tofu:plan/tofu:apply.
if len(sys.argv) > 1:
    plan = json.loads(run('tofu', '-chdir=lab/tofu/environments/lab', 'show', '-json', sys.argv[1]).stdout)
    values = {k: v['value'] for k, v in plan['variables'].items()}
    requested_memory, requested_cpu, requested_disk = (values[k] for k in ('memory', 'vcpu', 'disk_size'))
    cidr = values['management_cidr']
    host_count = values['host_count']
requested_memory *= host_count
requested_cpu *= host_count
requested_disk *= host_count
print(f'Budget cumulé pour {host_count} hôtes Hyper-V')
print(f'Disponible : {memory} Mio RAM ; {free_gib} Gio libres dans {storage_path}')
check(memory >= requested_memory + 4096, f'RAM demandée {requested_memory} Mio + réserve hôte 4096 Mio')
check((os.cpu_count() or 0) >= requested_cpu + 2, f'{requested_cpu} vCPU + réserve hôte 2 CPU')
check(free_gib >= requested_disk + 10, f'disque demandé {requested_disk} Gio + réserve 10 Gio')
check(shutil.which('ip') is not None, 'commande ip disponible (iproute2)')
if shutil.which('ip'):
    routes = run('ip', '-j', '-4', 'route', 'show', 'table', 'all')
    check(routes.returncode == 0, 'lecture des routes IPv4')
    network = ipaddress.ip_network(cidr)
    # The lab's own bridge is permitted on subsequent runs, by its actual libvirt definition.
    own_bridge = None
    if shutil.which('virsh'):
        import xml.etree.ElementTree as ET
        xml = run('virsh', '-c', 'qemu:///system', 'net-dumpxml', 'lab-management')
        if xml.returncode == 0:
            root = ET.fromstring(xml.stdout)
            bridge = root.find('bridge')
            own_bridge = bridge.get('name') if bridge is not None else None
    for route in json.loads(routes.stdout or '[]'):
        dst = route.get('dst', 'default')
        if dst == 'default' or route.get('dev') == own_bridge:
            continue
        if network.overlaps(ipaddress.ip_network(dst, strict=False)):
            check(False, f'{cidr} chevauche {dst} sur {route.get("dev")}')
if errors:
    print('Diagnostic en échec. Corriger les prérequis ; aucun paquet système installé automatiquement.', file=sys.stderr)
    sys.exit(1)
print('Prérequis Linux validés. Le démarrage Hyper-V/L2 reste à prouver dans Windows.')
