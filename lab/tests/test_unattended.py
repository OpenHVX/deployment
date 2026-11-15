import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location('prepare_windows', 'lab/scripts/prepare-windows.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
NS = {'u': module.NS}

class UnattendedTest(unittest.TestCase):
    def test_credentials_are_xml_escaped(self):
        password = 'aA1!<&"test-secret'
        xml = module.answer('lab-hv03', password, 4)
        root = ET.fromstring(xml)
        self.assertEqual(root.find('.//u:AdministratorPassword/u:Value', NS).text, password)
        self.assertEqual(root.find('.//u:ComputerName', NS).text, 'lab-hv03')
        self.assertEqual(root.find('.//u:MetaData/u:Value', NS).text, '4')
        self.assertEqual(root.find('.//u:InstallTo/u:PartitionID', NS).text, '3')
        self.assertIn('Initialize-LabWindows.ps1', root.find('.//u:RunSynchronousCommand/u:Path', NS).text)
        self.assertNotIn('__INJECT_', xml.decode())
