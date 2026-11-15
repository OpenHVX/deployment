"""Verify that the platform runner works without lab state or credentials."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class PlatformBoundaryTest(unittest.TestCase):
    def run_platform(self, inventory):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'scripts').mkdir()
            (root / 'bin').mkdir()
            shutil.copy2('scripts/deploy.sh', root / 'scripts/deploy.sh')
            (root / 'hosts.yml').write_text('all:\n  hosts: {}\n')
            fake = root / 'bin/ansible-playbook'
            fake.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@"\n')
            fake.chmod(0o755)
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(('LAB_', 'PLATFORM_', 'ANSIBLE_'))}
            env['PATH'] = str(root / 'bin') + os.pathsep + env['PATH']
            if inventory:
                env['PLATFORM_INVENTORY'] = str(root / 'hosts.yml')
            return subprocess.run(['bash', str(root / 'scripts/deploy.sh'), '--check'],
                                  env=env, text=True, capture_output=True)

    def test_explicit_inventory_without_lab(self):
        result = self.run_platform(True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ansible/playbooks/configure.yml', result.stdout)
        self.assertIn('--check', result.stdout)

    def test_missing_inventory_fails_before_ansible(self):
        result = self.run_platform(False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PLATFORM_INVENTORY', result.stderr)
        self.assertEqual(result.stdout, '')
