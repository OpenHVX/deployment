#!/usr/bin/env python3
"""Exercise logical VPC admission through the lab's public TLS/admin API."""
import json
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT/'.lab/infra'
BASE = 'https://admin-api.192-168-50-20.sslip.io'


def main():
    context = ssl.create_default_context(cafile=str(ROOT/'.lab/ca.pem'))
    token = ''

    def request(method, path, payload=None, key=None, expected=200):
        headers = {'Host': 'admin-api.openhvx.lab', 'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer '+token
        if key:
            headers['Idempotency-Key'] = key
        req = urllib.request.Request(BASE+path, method=method, headers=headers,
                                     data=json.dumps(payload).encode() if payload is not None else None)
        try:
            response = urllib.request.urlopen(req, context=context, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            if response.code != expected:
                raise RuntimeError(f'{method} {path}: expected {expected}, received {response.code}: '+raw.decode()[:500])
            return json.loads(raw) if raw else None

    login = request('POST', '/api/v1/admin/auth/login', json.loads((WORK/'admin.json').read_text()))
    token = login.get('access_token') or login.get('data', {}).get('access_token')
    if not token:
        raise RuntimeError('Admin authentication failed')
    tenant_id = 'network-poc-'+uuid.uuid4().hex[:12]
    root = '/api/v1/admin/tenants/'+tenant_id
    request('POST', '/api/v1/admin/tenants', {'tenantId': tenant_id, 'name': 'Disposable network acceptance', 'quotas': {'vpcCount': 2}}, expected=201)
    ids = []
    try:
        payload = {'name': 'Private VPC', 'cidr': '10.42.0.0/16'}
        one = request('POST', root+'/network/vpcs', payload, 'one', 201)['data']
        ids.append(one['vpcId'])
        assert one['state'] == 'planned'
        replay = request('POST', root+'/network/vpcs', payload, 'one', 201)['data']
        assert replay == one
        request('POST', root+'/network/vpcs', {**payload, 'name': 'Changed'}, 'one', 409)
        two = request('POST', root+'/network/vpcs', payload, 'two', 201)['data']
        ids.append(two['vpcId'])
        for vpc_id in ids:
            for attempt in range(30):
                plan = request('GET', root+'/network/vpcs/'+vpc_id+'/plan')['data']
                if plan['status'] == 'planned':
                    assert plan['ready'] is False and plan['plan']['mode'] == 'plan-only'
                    break
                time.sleep(1)
            else:
                raise RuntimeError('Network orchestrator did not return a persisted plan')
        request('POST', root+'/network/vpcs', payload, 'three', 409)
        listed = request('GET', root+'/network/vpcs')['data']
        assert {row['vpcId'] for row in listed} == set(ids)
        quotas = request('GET', root+'/quotas')
        # Quota endpoint exposes its result as data. Never print the login token.
        data = quotas.get('data', quotas)
        assert data['vpcCount']['used'] == 2
        request('PATCH', root, {'quotas': {'vpcCount': 2}})
        assert request('GET', root+'/quotas')['data']['vpcCount']['used'] == 2
        request('PATCH', root+'/quotas', {'limits': {'vpcCount': 0}})
        assert request('GET', root+'/network/vpcs/'+one['vpcId'])['data']['state'] == 'planned'
        request('POST', root+'/network/vpcs', payload, 'four', 409)
        request('DELETE', root, expected=409)
    finally:
        # All resources in this scenario are logical planned VPCs without host effects.
        for vpc_id in ids:
            request('DELETE', root+'/network/vpcs/'+vpc_id, expected=204)
        request('DELETE', root, expected=200)
    (WORK/'network-result.json').write_text(json.dumps({
        'tenantId': tenant_id, 'vpcIds': ids, 'idempotentReplay': True,
        'quotaEnforced': True, 'overlappingCidrs': True, 'cleanup': True,
        'providerForwardingTested': False, 'planningRoundtrip': True,
    }, indent=2)+'\n')
    print('Logical VPC API, asynchronous network planning, replay, quotas and cleanup verified through public TLS. No forwarding/HA claim.')


if __name__ == '__main__':
    main()
