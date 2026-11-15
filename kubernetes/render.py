#!/usr/bin/env python3
"""Render versioned Kustomize resources with private credentials, without applying them."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from jinja2 import Environment, StrictUndefined
import yaml

ROOT = Path(__file__).resolve().parents[1]


def render(work, ca, overlay):
    context = {
        'secrets': yaml.safe_load((work / 'secrets.yml').read_text()),
        'settings': yaml.safe_load((overlay / 'settings.yml').read_text()),
        'certificate': (work / 'ingress.crt').read_text(),
        'private_key': (work / 'ingress.key').read_text(),
        'ca': ca.read_text(),
    }
    for key in ['register_enabled', 'network_poc_enabled']:
        if context['settings'][key] not in ['true', 'false']:
            raise ValueError(f'{key} must be the string "true" or "false"')
    templates = Environment(undefined=StrictUndefined, autoescape=False)
    # A private staging tree lets Kustomize load credentials without allowing
    # arbitrary paths outside its root or storing secrets beside tracked sources.
    with tempfile.TemporaryDirectory(prefix='kustomize-', dir=work) as tmp:
        staging = Path(tmp)
        shutil.copytree(ROOT / 'kubernetes/base', staging / 'base')
        target = staging / 'overlays/lab'
        target.mkdir(parents=True)
        config = yaml.safe_load((overlay / 'kustomization.yaml').read_text())
        patches = []
        for source in sorted((overlay / 'private').glob('*.yaml.j2')):
            rendered = templates.from_string(source.read_text()).render(context)
            resource = yaml.safe_load(rendered)
            filename = source.name.removesuffix('.j2')
            (target / filename).write_text(rendered)
            config['resources'].append(filename)
            if resource['metadata']['name'].endswith('-env'):
                values = dict(resource['stringData'])
                # Preserve the existing rollout checksum during this migration.
                if 'PORT' in values:
                    values['PORT'] = int(values['PORT'])
                digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
                name = resource['metadata']['name'].removesuffix('-env')
                kind = 'StatefulSet' if name in ['mongo', 'rabbitmq', 'ws-broker'] else 'Deployment'
                patches.append({'patch': yaml.safe_dump({
                    'apiVersion': 'apps/v1', 'kind': kind,
                    'metadata': {'name': name, 'namespace': 'openhvx'},
                    'spec': {'template': {'metadata': {'annotations': {'openhvx.io/config-digest': digest}}}},
                })})
        config['patches'] = config.get('patches', []) + patches
        (target / 'kustomization.yaml').write_text(yaml.safe_dump(config, sort_keys=False))
        result = subprocess.run(['kustomize', 'build', str(target)], check=True, capture_output=True)
        # Atomic replacement; restrictive permissions exist before the first byte.
        fd, path = tempfile.mkstemp(prefix='openhvx-', suffix='.yml', dir=work)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(result.stdout)
            Path(path).replace(work / 'openhvx.yml')
        finally:
            Path(path).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--ca', required=True, type=Path)
    parser.add_argument('--overlay', type=Path, default=ROOT / 'kubernetes/overlays/lab')
    args = parser.parse_args()
    render(args.work.resolve(), args.ca.resolve(), args.overlay.resolve())
    print('Private Kubernetes manifest rendered; no resources applied.')


if __name__ == '__main__':
    main()
