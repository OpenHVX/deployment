#!/usr/bin/env python3
"""Cross-compile the Windows agent and helpers into a private deployment archive."""
import os
from pathlib import Path
import subprocess
import zipfile
ROOT=Path(__file__).resolve().parents[2]
source=ROOT.parent/'openhvx-agent'
work=ROOT/'.lab/infra/agent'
work.mkdir(parents=True,exist_ok=True)
env={**os.environ,'GOOS':'windows','GOARCH':'amd64','CGO_ENABLED':'0'}
for directory,target in [('src','openhvx-agent.exe'),('tools/cloudinit-iso/src','openhvx-cidata-iso.exe'),('tools/serial-bridge/src','openhvx-serial-bridge.exe')]:
 subprocess.run(['go','build','-trimpath','-o',str(work/target),'.'],cwd=source/directory,env=env,check=True)
with zipfile.ZipFile(ROOT/'.lab/infra/agent.zip','w',zipfile.ZIP_DEFLATED) as z:
 def add(path,name):
  info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
  z.writestr(info,path.read_bytes())
 add(work/'openhvx-agent.exe','openhvx-agent.exe')
 for name in ['openhvx-cidata-iso.exe','openhvx-serial-bridge.exe']:add(work/name,'powershell/bin/'+name)
 for p in sorted((source/'src/powershell').rglob('*.ps1')):
  if 'tests' not in p.parts:add(p,'powershell/'+str(p.relative_to(source/'src/powershell')))
print('Windows agent and helper archive prepared.')
