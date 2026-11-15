#!/usr/bin/env python3
"""Read a persisted controller command and its matching executor result; no queue consumption."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.lab/infra'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation-id', default='', help='Inspect this operation instead of the latest execution')
    args = parser.parse_args()
    # Pass identifiers as JSON stdin, never interpolate them into shell/JavaScript code.
    remote = r'''
import json,subprocess,sys
operation_id = json.loads(sys.stdin.readline())
base = ['sudo','k3s','kubectl','-n','openhvx','exec']
worker = "const m=require('mongoose');(async()=>{await m.connect(process.env.MONGO_URL);const q=process.argv[1]?{operationId:process.argv[1]}:{};const d=await m.connection.collection('networkexecutions').findOne(q,{sort:{createdAt:-1},projection:{_id:0,operationId:1,result:1}});console.log(JSON.stringify(d));await m.disconnect()})().catch(()=>{console.error('Executor journal read failed');process.exit(1)})"
w = json.loads(subprocess.check_output(base+['deployment/network-orchestrator','--','node','-e',worker,operation_id],text=True))
if not w: raise SystemExit('No matching network execution found')
controller = "const m=require('mongoose');(async()=>{await m.connect(process.env.MONGO_URL);const d=await m.connection.collection('networkoperations').findOne({operationId:process.argv[1]});if(!d)throw Error();console.log(JSON.stringify({contractVersion:2,eventId:d.eventId,commandBody:d.commandBody,commandFingerprint:d.commandFingerprint}));await m.disconnect()})().catch(()=>{console.error('Controller operation read failed');process.exit(1)})"
c = json.loads(subprocess.check_output(base+['deployment/controller','--','node','-e',controller,w['operationId']],text=True))
print(json.dumps({'controllerEnvelope':c,'decodedCommand':json.loads(c['commandBody']),'orchestratorResult':w['result']},indent=2))
'''
    # Python -c keeps stdin available for the JSON argument. The remote source is
    # shell-quoted independently; the operation identifier never enters that source.
    import shlex
    command = 'python3 -c '+shlex.quote(remote)
    subprocess.run(['ssh', '-i', str(WORK/'id_ed25519'), '-o', 'BatchMode=yes',
                    '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile='+str(WORK/'known_hosts'),
                    'ubuntu@192.168.50.21', command], input=json.dumps(args.operation_id)+'\n', text=True, check=True)


if __name__ == '__main__':
    main()
