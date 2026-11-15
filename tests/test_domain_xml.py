import pathlib
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET

class DomainXmlTest(unittest.TestCase):
    def test_q35_iso_drives_use_unique_sata_targets(self):
        self.assertIsNotNone(shutil.which('xsltproc'), 'Installer libxslt pour vérifier la transformation Q35')
        source = '''<domain><devices>
          <controller type="ide" index="0"/>
          <disk device="disk"><target dev="vda" bus="virtio"/></disk>
          <disk device="cdrom"><target dev="hda" bus="ide"/><address type="drive" controller="0"/></disk>
          <disk device="cdrom"><target dev="hdb" bus="ide"/><address type="drive" controller="0"/></disk>
        </devices></domain>'''
        result = subprocess.run(['xsltproc', 'tofu/modules/windows-vm/windows-domain.xsl', '-'],
                                input=source, text=True, capture_output=True, check=True)
        root = ET.fromstring(result.stdout)
        self.assertIsNone(root.find("devices/controller[@type='ide']"))
        self.assertEqual(root.find("devices/disk[@device='disk']/target").attrib, {'dev': 'vda', 'bus': 'virtio'})
        drives = root.findall("devices/disk[@device='cdrom']")
        self.assertEqual([d.find('target').attrib for d in drives],
                         [{'bus': 'sata', 'dev': 'sda'}, {'bus': 'sata', 'dev': 'sdb'}])
        self.assertTrue(all(d.find('address') is None for d in drives))
