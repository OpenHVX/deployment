#!/usr/bin/env python3
"""Snapshot sibling source repositories without local secrets or build caches."""
import hashlib
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[2]
work=ROOT/'.lab/infra/build'
work.mkdir(parents=True,exist_ok=True)
digest=hashlib.sha256()
for name in ['auth','api-gateway','controller','ws-broker','network-orchestrator','ceph-connector']:
    source=ROOT.parent/('openhvx-ceph-connector' if name=='ceph-connector' else 'openhvx-backend/src/service-'+name)
    target=work/(name+'.tgz')
    subprocess.run(['tar','--exclude=node_modules','--exclude=.git','--exclude=.env*','--exclude=dist','--exclude=*.log','-czf',str(target),'-C',str(source),'.'],check=True)
    # Source content, not archive timestamps, determines the deployment version.
    for p in sorted(source.rglob('*')):
        if not p.is_file() or any(x in ['node_modules','.git','dist'] for x in p.relative_to(source).parts) or p.name.startswith('.env') or p.suffix=='.log':continue
        digest.update((name+'/'+str(p.relative_to(source))).encode());digest.update(p.read_bytes())
(ROOT/'.lab/infra/image-tag').write_text('lab-'+digest.hexdigest()[:12]+'\n')
print('Source snapshots prepared without environment files.')
