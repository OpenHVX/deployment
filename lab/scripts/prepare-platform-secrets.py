#!/usr/bin/env python3
"""Prepare persistent lab credentials and CA-signed service certificates.

A rerun reuses identities. Missing credentials on an existing installation are a
recovery problem, never permission to generate a replacement database password.
Certificate requests are public metadata; private keys and credentials stay local.
"""
import os
import secrets
import subprocess

import yaml
from lab_runtime import ROOT, WORK, ensure_lab_lock

SECRET_NAMES = (
    'k3s_token', 'ceph_dashboard_password', 'ceph_iscsi_password', 'mongo_password',
    'rabbit_password', 'JWT_TENANT_SECRET', 'JWT_ADMIN_SECRET', 'JWT_AGENT_SECRET',
    'JWT_BROWSER_SECRET', 'INTERNAL_API_SECRET', 'OUTBOX_ENCRYPTION_KEY', 'REGISTER_API_KEY',
)


def prepare_credentials():
    path = WORK / 'secrets.yml'
    if path.exists():
        return
    if (WORK / 'linux.yml').exists():
        raise ValueError('Service credentials are missing for an existing installation; restore secrets.yml from backup')
    values = {name: secrets.token_hex(32) for name in SECRET_NAMES}
    # Restrict access before writing the first credential, not after it is saved.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        yaml.safe_dump(values, output)


def certificate_specifications():
    domains = ('api', 'admin-api', 'console', 'ws')
    return (
        ('dashboard', 'openhvx-ceph-01',
         [f'IP:192.168.50.{i}' for i in range(30, 34)]
         + [f'DNS:openhvx-ceph-{i:02d}' for i in range(1, 4)]),
        ('ingress', 'api.openhvx.lab',
         [f'DNS:{name}.openhvx.lab' for name in domains]
         + [f'DNS:{name}.192-168-50-20.sslip.io' for name in domains]
         + [f'IP:192.168.50.{i}' for i in range(20, 24)]),
    )


def prepare_certificate(name, common_name, alternative_names):
    extension = WORK / (name + '.ext')
    desired = 'subjectAltName=' + ','.join(alternative_names) + '\nextendedKeyUsage=serverAuth\n'
    certificate = WORK / (name + '.crt')
    key = WORK / (name + '.key')
    if certificate.exists() and not key.exists():
        raise ValueError(f'{name} certificate key is missing; restore the existing key before continuing')
    if extension.exists() and extension.read_text() == desired and certificate.exists():
        return
    pending_extension = WORK / (name + '.ext.partial')
    pending_certificate = WORK / (name + '.crt.partial')
    pending_extension.write_text(desired)
    request = WORK / (name + '.csr')
    command = ['openssl', 'req', '-new', '-out', str(request), '-subj', '/CN=' + common_name]
    if key.exists():
        command += ['-key', str(key)]
    else:
        command += ['-newkey', 'rsa:2048', '-nodes', '-keyout', str(key)]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([
        'openssl', 'x509', '-req', '-in', str(request),
        '-CA', str(ROOT / '.lab/ca.pem'), '-CAkey', str(ROOT / '.lab/ca.key'),
        '-CAcreateserial', '-out', str(pending_certificate), '-days', '365', '-extfile', str(pending_extension),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    key.chmod(0o600)
    # Publish the certificate before its specification receipt. If signing fails,
    # the previous receipt stays intact so the next invocation retries issuance.
    pending_certificate.replace(certificate)
    pending_extension.replace(extension)


def main():
    ensure_lab_lock()
    os.umask(0o077)
    WORK.mkdir(parents=True, exist_ok=True)
    if not (ROOT / '.lab/ca.key').exists():
        raise ValueError('Lab CA key missing. Prepare Windows first, or restore the CA for an existing lab.')
    prepare_credentials()
    for specification in certificate_specifications():
        prepare_certificate(*specification)
    print('Persistent lab credentials and certificates ready; existing secret values preserved.')


if __name__ == '__main__':
    main()
