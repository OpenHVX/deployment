#!/usr/bin/env python3
"""Generate persistent lab secrets and CA-signed infrastructure certificates."""
from pathlib import Path
import secrets
import subprocess
import yaml
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'.lab/infra'

def main():
    WORK.mkdir(parents=True,exist_ok=True)
    path=WORK/'secrets.yml'
    if not path.exists():
        path.write_text(yaml.safe_dump({k:secrets.token_hex(32) for k in ['k3s_token','ceph_dashboard_password','ceph_iscsi_password','mongo_password','rabbit_password','JWT_TENANT_SECRET','JWT_ADMIN_SECRET','JWT_AGENT_SECRET','JWT_BROWSER_SECRET','INTERNAL_API_SECRET','OUTBOX_ENCRYPTION_KEY','REGISTER_API_KEY']}))
        path.chmod(0o600)
    if not (ROOT/'.lab/ca.key').exists():
        raise SystemExit('Run windows:prepare first; the lab CA is required.')
    domains=['api','admin-api','console','ws']
    specs=[('dashboard','openhvx-ceph-01',[f'IP:192.168.50.{30+i}' for i in range(0,4)]+[f'DNS:openhvx-ceph-{i:02d}' for i in range(1,4)]),('ingress','api.openhvx.lab',[f'DNS:{x}.openhvx.lab' for x in domains]+[f'DNS:{x}.192-168-50-20.sslip.io' for x in domains]+[f'IP:192.168.50.{i}' for i in range(20,24)])]
    for name,cn,sans in specs:
        ext=WORK/(name+'.ext')
        desired='subjectAltName='+','.join(sans)+'\nextendedKeyUsage=serverAuth\n'
        if ext.exists() and ext.read_text()==desired and (WORK/(name+'.crt')).exists():continue
        ext.write_text(desired)
        key=WORK/(name+'.key');csr=WORK/(name+'.csr')
        cmd=['openssl','req','-new','-out',str(csr),'-subj','/CN='+cn]
        if key.exists():cmd+=['-key',str(key)]
        else:cmd+=['-newkey','rsa:2048','-nodes','-keyout',str(key)]
        subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run(['openssl','x509','-req','-in',str(csr),'-CA',str(ROOT/'.lab/ca.pem'),'-CAkey',str(ROOT/'.lab/ca.key'),'-CAcreateserial','-out',str(WORK/(name+'.crt')),'-days','365','-extfile',str(ext)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        key.chmod(0o600)
    print('Persistent lab secrets and certificates ready; existing secret values preserved.')
if __name__=='__main__':main()
