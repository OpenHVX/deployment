"""Check the HA deployment contract without reading real lab secrets."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import yaml


class KubernetesRenderTest(unittest.TestCase):
    def test_replica_placement_broker_identity_and_private_output(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            keys = ['mongo_password', 'rabbit_password', 'JWT_TENANT_SECRET',
                    'JWT_ADMIN_SECRET', 'JWT_AGENT_SECRET', 'JWT_BROWSER_SECRET',
                    'INTERNAL_API_SECRET', 'OUTBOX_ENCRYPTION_KEY', 'REGISTER_API_KEY',
                    'ceph_dashboard_password']
            (work / 'secrets.yml').write_text(yaml.safe_dump({k: "test'\"\nonly-placeholder" for k in keys}))
            # Obsolete private controls must not override the declared release.
            (work / 'image-tag').write_text('test-only')
            (work / 'image-overrides.json').write_text('{"controller":"query-fix"}')
            for name in ['ingress.crt', 'ingress.key', 'ca.pem']:
                (work / name).write_text('test-only-placeholder')
            (work / 'network-settings.json').write_text('{"pocEnabled":false}')
            subprocess.run([sys.executable, 'kubernetes/render.py', '--work',
                            str(work), '--ca', str(work / 'ca.pem')], check=True, capture_output=True)
            output = work / 'openhvx.yml'
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            objects = {(o['kind'], o['metadata']['name']): o
                       for o in yaml.safe_load_all(output.read_text())}
            for name in ['mongo', 'rabbitmq', 'ws-broker']:
                spec = objects['StatefulSet', name]['spec']
                self.assertEqual(spec['replicas'], 3)
                self.assertIn('requiredDuringSchedulingIgnoredDuringExecution',
                              spec['template']['spec']['affinity']['podAntiAffinity'])
            for name, tag in [('controller', 'lab-5e357079def7'), ('auth', 'lab-7269b72fa206')]:
                image = objects['Deployment', name]['spec']['template']['spec']['containers'][0]['image']
                self.assertEqual(image, f'openhvx/{name}:{tag}')
            broker = objects['StatefulSet', 'ws-broker']['spec']['template']['spec']['containers'][0]
            self.assertEqual(broker['env'][0]['valueFrom']['fieldRef']['fieldPath'], 'metadata.name')
            connector = objects['Deployment', 'ceph-connector']['spec']
            self.assertEqual(connector['strategy']['type'], 'Recreate')
            self.assertEqual(objects['Secret', 'ceph-connector-env']['stringData']['CEPH_API_URL'],
                             'https://192.168.50.30:8443')
            self.assertEqual(objects['Secret', 'auth-env']['stringData']['REGISTER_ENABLED'], 'false')
            password = objects['Secret', 'mongo-env']['stringData']['MONGO_INITDB_ROOT_PASSWORD']
            self.assertEqual(password, "test'\"\nonly-placeholder")
            values = dict(objects['Secret', 'controller-env']['stringData'])
            values['PORT'] = int(values['PORT'])
            digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
            self.assertEqual(objects['Deployment', 'controller']['spec']['template']['metadata']['annotations']['openhvx.io/config-digest'], digest)
            traefik = yaml.safe_load(objects['HelmChartConfig', 'traefik']['spec']['valuesContent'])
            self.assertEqual(traefik['deployment']['kind'], 'DaemonSet')

            self.assertEqual(objects['Deployment', 'network-orchestrator']['spec']['replicas'], 3)
            self.assertIn('/openhvx-network?', objects['Secret', 'network-orchestrator-env']['stringData']['MONGO_URL'])
            self.assertEqual(objects['Secret', 'controller-env']['stringData']['NETWORK_POC_ENABLED'], 'true')
