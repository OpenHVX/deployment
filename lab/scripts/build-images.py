#!/usr/bin/env python3
"""Build/import source snapshots; leave the declared release unchanged."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.lab/infra'


def main():
    subprocess.run([sys.executable, str(ROOT / 'lab/scripts/prepare-images.py')], check=True)
    tag = (WORK / 'image-tag').read_text().strip()
    subprocess.run([str(ROOT / 'scripts/deploy.sh'), '-e', 'infra_work=' + str(WORK),
                    '-e', 'image_tag=' + tag], cwd=ROOT, check=True, env={**os.environ,
                       'PLATFORM_INVENTORY': str(WORK / 'linux.yml'),
                       'PLATFORM_PLAYBOOK': 'ansible/playbooks/images.yml'})
    print('Images imported with tag ' + tag + '. Review/promote in kubernetes/overlays/lab/kustomization.yaml before deploying.')


if __name__ == '__main__':
    main()
