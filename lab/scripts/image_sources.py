#!/usr/bin/env python3
"""Snapshot application sources into a new, private release directory.

A source hash is provenance, not an image digest: upstream base images can change.
Every build therefore gets a new release tag, even when its sources are unchanged.
The build role refuses to overwrite that tag on any K3s node.
"""
import argparse
import hashlib
import subprocess
import uuid

from lab_runtime import ROOT, WORK, ensure_lab_lock

SERVICES = ('auth', 'api-gateway', 'controller', 'ws-broker',
            'network-orchestrator', 'ceph-connector')
EXCLUDED = {'.git', 'node_modules', 'dist'}


def source_directory(name):
    if name == 'ceph-connector':
        return ROOT.parent / 'openhvx-ceph-connector'
    return ROOT.parent / 'openhvx-backend/src' / ('service-' + name)


def included(path):
    return not any(part in EXCLUDED or part.startswith('.env') or part.endswith('.log')
                   for part in path.parts)


def prepare_release():
    # Validate all repositories before creating a partially populated release.
    for name in SERVICES:
        if not source_directory(name).is_dir():
            raise FileNotFoundError(f'Missing source repository: {source_directory(name)}')
    tag = 'lab-' + uuid.uuid4().hex
    release = WORK / 'releases' / tag
    build = release / 'build'
    build.mkdir(parents=True, mode=0o700)
    digest = hashlib.sha256()
    for name in SERVICES:
        source = source_directory(name)
        # Hash the archive's input files, including file names, before packaging.
        # This records the candidate's sources; immutable image IDs are recorded
        # later by Docker, after the actual build succeeds.
        for path in sorted(source.rglob('*')):
            relative = path.relative_to(source)
            if path.is_file() and included(relative):
                digest.update((name + '/' + str(relative)).encode())
                digest.update(path.read_bytes())
        subprocess.run([
            'tar', '--exclude=node_modules', '--exclude=.git', '--exclude=.env*',
            '--exclude=dist', '--exclude=*.log', '-czf', str(build / (name + '.tgz')),
            '-C', str(source), '.',
        ], check=True)
    (release / 'source-sha256').write_text(digest.hexdigest() + '\n')
    return tag, release


def main():
    ensure_lab_lock()
    argparse.ArgumentParser(description=__doc__).parse_args()
    tag, release = prepare_release()
    print(f'Source candidate prepared: {tag}\nArtifacts: {release}')
    print('No images built or imported. Use lab:images:build for the complete build.')


if __name__ == '__main__':
    main()
