import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/prepare-vyos.py'
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location('prepare_vyos', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VyosBootstrapTests(unittest.TestCase):
    def test_bootstrap_rejects_key_material_that_could_inject_cli_commands(self):
        node = module.topology()[0]
        for key in ["ssh-rsa AAAA", "ssh-ed25519 AAAA'\nset service telnet", "PRIVATE KEY"]:
            with self.assertRaises(ValueError):
                module.bootstrap(node, key)

    def test_missing_image_manifest_fails_before_preparing_or_changing_hosts(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cloud-init VHDX', result.stderr)


if __name__ == '__main__':
    unittest.main()
