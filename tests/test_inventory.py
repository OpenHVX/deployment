import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

class InventoryTest(unittest.TestCase):
    def generate(self, hosts):
        # Run the generator in an isolated copy; preserve the real inventory.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'lab/scripts').mkdir(parents=True)
            (root / 'environments/lab').mkdir(parents=True)
            script = root / 'lab/scripts/generate-inventory.py'
            script.write_text(Path('lab/scripts/generate-inventory.py').read_text())
            result = subprocess.run(['python3', str(script)], input=json.dumps({
                'ansible_hosts': {'value': hosts},
                'management_cidr': {'value': '192.168.50.0/24'}
            }), capture_output=True, text=True)
            target = root / '.lab/hosts.yml'
            return result, target.read_text() if target.exists() else None

    def test_tls_and_credentials(self):
        result, content = self.generate({'lab-hv01': {'ansible_host': '192.168.50.10'}})
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(content)['all']
        self.assertEqual(data['hosts']['lab-hv01']['ansible_host'], '192.168.50.10')
        self.assertEqual(data['vars']['ansible_winrm_server_cert_validation'], 'validate')
        self.assertIn("lookup('env'", data['vars']['ansible_password'])

    def test_empty_output_rejected(self):
        result, content = self.generate({})
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(content)

    def test_invalid_ip_rejected(self):
        result, content = self.generate({'lab-hv01': {'ansible_host': 'invalid'}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(content)

    def test_three_hosts(self):
        hosts = {f'lab-hv{i:02d}': {'ansible_host': f'192.168.50.{9+i}'} for i in range(1, 4)}
        result, content = self.generate(hosts)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(content)['all']['hosts'], hosts)
