"""Check the explicit destruction boundary without contacting any host."""
import importlib.util
import io
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('vyos_down', SCRIPTS/'vyos-down.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
IDENTITY = '11111111-1111-4111-8111-111111111111'


class VyosLifecycleTest(unittest.TestCase):
    def test_apply_requires_exact_deployment_identity_before_contacting_hosts(self):
        with patch.object(module, 'load_declaration', return_value={'vyos_deployment_id': IDENTITY}), \
             patch.object(module, 'playbook') as execute, \
             patch.object(sys, 'argv', ['vyos-down.py', '--apply', '--confirm', 'other']):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                module.main()
            self.assertEqual(error.exception.code, 2)
            execute.assert_not_called()

    def test_default_is_a_read_only_preview_of_selected_host(self):
        with patch.object(module, 'load_declaration', return_value={'vyos_deployment_id': IDENTITY}), \
             patch.object(module, 'playbook') as execute, \
             patch.object(sys, 'argv', ['vyos-down.py', '--host', 'lab-hv01']):
            with redirect_stdout(io.StringIO()):
                module.main()
            execute.assert_called_once_with('vyos-down', 'lab-hv01', {'vyos_destroy_apply': False})


if __name__ == '__main__':
    unittest.main()
