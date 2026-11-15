#!/usr/bin/env python3
"""Capture private control-plane and journal backups during a quiet lab period."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'.lab/infra'
SSH=['ssh','-i',str(WORK/'id_ed25519'),'-o','UserKnownHostsFile='+str(WORK/'known_hosts'),'-o','BatchMode=yes','ubuntu@192.168.50.21']

def remote(command,output=None):
    return subprocess.run(SSH+[command],check=True,stdout=output or subprocess.PIPE,stderr=subprocess.PIPE)

def main():
    os.umask(0o077)
    directory=WORK/'backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    directory.mkdir(parents=True,mode=0o700)
    auth='mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin'
    check=auth+''' --eval 'const n=db.getSiblingDB("hvwm").tasks.countDocuments({status:{$in:["queued","sent","reconciling"]}}); print(n); if(n)quit(1)' '''
    remote('sudo k3s kubectl -n openhvx exec mongo-0 -- sh -c '+shlex.quote(check))
    dump='mongodump --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --oplog --gzip --archive'
    with (directory/'mongo.archive.gz').open('wb') as output:
        remote('sudo k3s kubectl -n openhvx exec mongo-0 -- sh -c '+shlex.quote(dump),output)
    remote('sudo k3s etcd-snapshot save --name openhvx-lab')
    snapshot=remote("sudo find /var/lib/rancher/k3s/server/db/snapshots -type f -name 'openhvx-lab-*' -printf '%T@ %p\\n' | sort -n | tail -1 | cut -d' ' -f2-").stdout.decode().strip()
    if not snapshot.startswith('/var/lib/rancher/k3s/server/db/snapshots/'):raise RuntimeError('No etcd snapshot found')
    for source,name in [(snapshot,'etcd.snapshot'),('/var/lib/rancher/k3s/server/token','k3s-token')]:
        with (directory/name).open('wb') as output:remote('sudo cat '+shlex.quote(source),output)
    for source in [ROOT/'.lab/ca.pem',ROOT/'.lab/ca.key',WORK/'secrets.yml',WORK/'id_ed25519',WORK/'linux.yml',WORK/'windows-vars.yml',WORK/'image-tag']:
        shutil.copyfile(source,directory/source.name)
    subprocess.run([str(ROOT/'lab/scripts/run-platform.sh'),'-e','backup_dir='+str(directory)],cwd=ROOT,env={**os.environ,'PLATFORM_PLAYBOOK':'platform/ansible/playbooks/backup-agent.yml'},check=True)
    (directory/'metadata.json').write_text(json.dumps({'kind':'lab-control-plane-checkpoint','createdAt':datetime.now(timezone.utc).isoformat(),'mongoOplogIncluded':True,'windowsJournalsQuiesced':True,'cephOSDDataIncluded':False,'restoreTested':False},indent=2)+'\n')
    print('Private checkpoint saved:',directory)
    print('Ceph/tenant disks are not included; this is not a tested disaster-recovery backup.')
if __name__=='__main__':main()
