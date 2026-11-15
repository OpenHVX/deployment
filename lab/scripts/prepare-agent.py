#!/usr/bin/env python3
"""Cross-compile the Windows agent and package its existing PowerShell helpers.

This prepares an artifact only. Installation/restart is a separate Ansible stage,
inside the deployment maintenance window. Runtime journals are never packaged.
"""
import os
import subprocess
import zipfile

from lab_runtime import ROOT, WORK, ensure_lab_lock

SOURCE = ROOT.parent / 'openhvx-agent'
BINARIES = (
    ('src', 'openhvx-agent.exe'),
    ('tools/cloudinit-iso/src', 'openhvx-cidata-iso.exe'),
    ('tools/serial-bridge/src', 'openhvx-serial-bridge.exe'),
)


def add_file(archive, path, name):
    # ZIP timestamps are fixed so identical compiled bytes do not trigger agent
    # replacement merely because the package was assembled at another time.
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, path.read_bytes())


def main():
    ensure_lab_lock()
    build = WORK / 'agent'
    build.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, 'GOOS': 'windows', 'GOARCH': 'amd64', 'CGO_ENABLED': '0'}
    for directory, filename in BINARIES:
        subprocess.run(['go', 'build', '-trimpath', '-o', str(build / filename), '.'],
                       cwd=SOURCE / directory, env=environment, check=True)
    temporary = WORK / 'agent.zip.partial'
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            add_file(archive, build / 'openhvx-agent.exe', 'openhvx-agent.exe')
            for _, filename in BINARIES[1:]:
                add_file(archive, build / filename, 'powershell/bin/' + filename)
            helpers = SOURCE / 'src/powershell'
            for path in sorted(helpers.rglob('*.ps1')):
                if 'tests' not in path.relative_to(helpers).parts:
                    add_file(archive, path, 'powershell/' + str(path.relative_to(helpers)))
        temporary.replace(WORK / 'agent.zip')
    finally:
        temporary.unlink(missing_ok=True)
    print('Windows agent package prepared; no agent installed or restarted.')


if __name__ == '__main__':
    main()
