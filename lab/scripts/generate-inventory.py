#!/usr/bin/env python3
"""Produce deterministic inventory from tofu outputs; never include credentials."""
import ipaddress
import json
import os
from pathlib import Path
import sys
import yaml

outputs = json.load(sys.stdin)
hosts = outputs["ansible_hosts"]["value"]
if not hosts:
    raise SystemExit("Aucun hôte dans les outputs OpenTofu.")
for name, host in hosts.items():
    ipaddress.ip_address(host["ansible_host"])
    if not name or not isinstance(host, dict):
        raise SystemExit("Hôte invalide.")
environment = Path(__file__).resolve().parents[2] / "environments/lab/inventory.yml"
if environment.exists():
    declared = yaml.safe_load(environment.read_text())["all"]["children"]["hyperv"]["hosts"]
    if declared != hosts:
        raise SystemExit("OpenTofu outputs differ from environments/lab/inventory.yml; reconcile explicitly.")
result = {"all": {"hosts": hosts, "vars": {
    "management_cidr": outputs["management_cidr"]["value"],
    "ansible_user": "{{ lookup('env', 'LAB_WINDOWS_USER') | default('Administrator', true) }}",
    "ansible_password": "{{ lookup('env', 'LAB_WINDOWS_PASSWORD') }}",
    "ansible_connection": "winrm", "ansible_port": 5986,
    "ansible_winrm_scheme": "https", "ansible_winrm_transport": "ntlm",
    "ansible_winrm_server_cert_validation": "validate"}}}
target = Path(__file__).resolve().parents[2] / ".lab/hosts.yml"
target.parent.mkdir(parents=True, exist_ok=True)
tmp = target.with_suffix(".tmp")
tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
os.chmod(tmp, 0o600)
tmp.replace(target)
