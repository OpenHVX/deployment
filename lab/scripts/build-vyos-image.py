#!/usr/bin/env python3
"""Build an installed UEFI/cloud-init VyOS VHDX in an isolated, unprivileged QEMU guest."""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import re
import shutil
import subprocess
import sys

import pexpect

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT/'.lab/network/image-build'
PROMPT = 'OPENHVX-BUILD> '
FACTORY_VERSION = 3


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url, digest, path):
    if not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest):
        raise ValueError('Expected a SHA256 hex digest')
    if not path.exists():
        temporary = path.with_suffix('.download')
        subprocess.run(['curl', '--fail', '--location', '--retry', '3', '--silent', '--show-error',
                        '--proto', '=https', '--output', str(temporary), '--', url], check=True)
        if sha256(temporary) != digest:
            raise ValueError('Downloaded artifact checksum mismatch')
        temporary.replace(path)
    if sha256(path) != digest:
        raise ValueError('Cached artifact checksum mismatch')


def boot(disk, firmware, log, iso=None):
    command = ['-enable-kvm', '-machine', 'q35', '-cpu', 'host', '-m', '2048', '-smp', '2',
               '-drive', 'if=pflash,format=raw,readonly=on,file='+str(firmware),
               '-drive', 'if=pflash,format=raw,file='+str(WORK/'OVMF_VARS.fd'),
               '-drive', 'if=virtio,format=qcow2,file='+str(disk),
               '-nic', 'user,model=virtio-net-pci', '-display', 'none', '-serial', 'stdio',
               '-monitor', 'none', '-no-reboot']
    if iso:
        command += ['-cdrom', str(iso), '-boot', 'd']
    child = pexpect.spawn('qemu-system-x86_64', command, encoding='utf-8', codec_errors='replace', timeout=240)
    child.logfile_read = log
    if iso:
        child.expect('Serial console')
        child.send('\x1b[B\x1b[B\r')
    child.expect('login:')
    return child


def login(child, password):
    child.sendline('vyos')
    child.expect('Password:')
    child.sendline(password)
    child.expect(r'vyos@[^\r\n]+\$ ')
    child.sendline('sudo bash --noprofile --norc')
    child.expect(r'bash-[0-9.]+# ')
    child.sendline('stty -echo')
    child.expect(r'bash-[0-9.]+# ')
    child.sendline("export PS1='OPENHVX-BUILD> '")
    child.expect_exact(PROMPT)


def run_guest(child, source, timeout=240):
    payload = base64.b64encode(source.encode()).decode()
    if len(payload) > 3500:
        raise ValueError('Guest stage exceeds safe serial line length; split the stage')
    child.sendline("printf '%s' '"+payload+"' | base64 -d | bash; printf '\\nOPENHVX_RC:%s\\n' \"$?\"")
    child.expect(r'[\r\n]+OPENHVX_RC:([0-9]+)[\r\n]+', timeout=timeout)
    code = int(child.match.group(1))
    child.expect_exact(PROMPT)
    if code:
        raise RuntimeError(f'Guest stage failed ({code}); inspect {WORK}/build.log')


def install(child, password):
    child.sendline('python3 /usr/libexec/vyos/op_mode/image_installer.py --action install')
    prompts = [
        (r'Would you like to continue\?', 'y'),
        (r'What would you like to name this image\?', ''),
        (r'Please enter a password for the "vyos" user:', password),
        (r'Please confirm password for the "vyos" user:', password),
        (r'What console should be used by default\?', 'S'),
        (r'Which one should be used for installation\?', ''),
        (r'Installation will delete all data on the drive\. Continue\?', 'y'),
        (r'Would you like to use all the free space on the drive\?', 'y'),
        (r'Which file would you like as boot config\?', ''),
    ]
    patterns = [pattern for pattern, _ in prompts] + ['The image installed successfully', 'Unable to install VyOS:', PROMPT]
    while True:
        index = child.expect(patterns, timeout=240)
        if index == len(prompts):
            child.expect_exact(PROMPT)
            return
        if index > len(prompts):
            raise RuntimeError('VyOS installer failed; inspect build.log')
        child.sendline(prompts[index][1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'environments/lab/network/vyos-iso.json')
    parser.add_argument('--firmware', type=Path, default=Path('/usr/share/edk2/x64/OVMF_CODE.4m.fd'))
    parser.add_argument('--firmware-vars', type=Path, default=Path('/usr/share/edk2/x64/OVMF_VARS.4m.fd'))
    parser.add_argument('--rebuild', action='store_true', help='Replace this tool\'s disposable builder disk; never any Hyper-V guest')
    args = parser.parse_args()
    source = json.loads(args.source.read_text())
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK/'build.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output = WORK/'vyos-cloud-init.vhdx'
        manifest = ROOT/'.lab/network/image.json'
        if manifest.exists() and not args.rebuild:
            saved = json.loads(manifest.read_text())
            if saved.get('factoryVersion') != FACTORY_VERSION or saved.get('source') != source or not output.exists() or sha256(output) != saved['sha256']:
                raise ValueError('Existing build differs; inspect before using --rebuild')
            print(f'Verified image reused: {manifest}')
            return
        for tool in ['curl', 'qemu-img', 'qemu-system-x86_64']:
            if not shutil.which(tool):
                raise ValueError(f'Missing {tool}')
        if not os.access('/dev/kvm', os.R_OK | os.W_OK):
            raise ValueError('Read/write access to /dev/kvm is required')
        if not args.firmware.is_file() or not args.firmware_vars.is_file():
            raise ValueError('Supply matching OVMF code/vars paths')
        iso = WORK/'vyos.iso'
        download(source['url'], source['sha256'], iso)
        cloud = source['cloudInit']
        # Verify package availability and checksum before starting an installation.
        download(cloud['url'], cloud['sha256'], WORK/'cloud-init.deb')
        disk = WORK/'builder.qcow2'
        if disk.exists():
            if not args.rebuild:
                raise ValueError('Builder disk exists; inspect build.log, then use --rebuild explicitly')
            subprocess.run(['qemu-img', 'info', str(disk)], check=True, stdout=subprocess.DEVNULL)
            disk.unlink()
        shutil.copyfile(args.firmware_vars, WORK/'OVMF_VARS.fd')
        subprocess.run(['qemu-img', 'create', '-f', 'qcow2', str(disk), '10G'], check=True)
        password = secrets.token_urlsafe(32)+'aA1!'
        child = None
        with (WORK/'build.log').open('w') as log:
            try:
                print('Installing pinned VyOS in disposable QEMU guest...', flush=True)
                child = boot(disk, args.firmware, log, iso)
                login(child, 'vyos')
                install(child, password)
                child.sendline('poweroff')
                child.expect(pexpect.EOF, timeout=120)
                child.close()
                print('Installing pinned VyOS cloud-init in the installed guest...', flush=True)
                child = boot(disk, args.firmware, log)
                login(child, password)
                run_guest(child, '''set -e
ip link set eth0 up
ip address add 10.0.2.15/24 dev eth0 || true
ip route replace default via 10.0.2.2
printf 'nameserver 10.0.2.3\\n' > /etc/resolv.conf
printf 'deb https://deb.debian.org/debian bookworm main\\n' > /etc/apt/sources.list.d/openhvx-build.list
apt-get update >/tmp/openhvx-apt.log 2>&1
''')
                run_guest(child, f'''set -e
curl --fail --location --connect-timeout 10 --max-time 60 --silent --show-error {shlex.quote(cloud['url'])} -o /tmp/openhvx-cloud-init.deb
printf '%s\\n' {shlex.quote(cloud['sha256']+'  /tmp/openhvx-cloud-init.deb')} | sha256sum -c -
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends /tmp/openhvx-cloud-init.deb ifupdown cloud-guest-utils >/tmp/openhvx-install.log 2>&1
''', timeout=600)
                run_guest(child, '''set -e
python3 -c 'import cloudinit.config.cc_vyos'
printf 'datasource_list: [ NoCloud ]\\n' > /etc/cloud/cloud.cfg.d/90-openhvx-datasource.cfg
systemctl enable cloud-init-local.service cloud-init.service cloud-config.service cloud-final.service
rm -f /etc/apt/sources.list.d/openhvx-build.list /tmp/openhvx-cloud-init.deb
apt-get clean
rm -rf /var/lib/apt/lists/* /var/lib/cloud /opt/vyatta/etc/config/cloud
''')
                run_guest(child, '''set -e
usermod --password '*' vyos
python3 - <<'INNER'
from pathlib import Path
from vyos.configtree import ConfigTree
p=Path('/config/config.boot')
c=ConfigTree(p.read_text())
c.set(['system','login','user','vyos','authentication','encrypted-password'], '*')
if c.exists(['interfaces','ethernet']):
    c.delete(['interfaces','ethernet'])
from vyos.defaults import directories
(Path(directories['config'])/'interface-mapping.json').unlink(missing_ok=True)
p.write_text(c.to_string())
INNER
rm -f /etc/ssh/ssh_host_* /root/.bash_history /home/vyos/.bash_history
truncate -s 0 /etc/machine-id
sync
''')
                child.sendline('poweroff')
                child.expect(pexpect.EOF, timeout=120)
                child.close()
            finally:
                if child and child.isalive():
                    child.terminate(force=True)
        temporary = WORK/'vyos-cloud-init.partial.vhdx'
        subprocess.run(['qemu-img', 'convert', '-f', 'qcow2', '-O', 'vhdx', str(disk), str(temporary)], check=True)
        temporary.replace(output)
        manifest.write_text(json.dumps({'version': source['version'], 'image': str(output),
                                        'sha256': sha256(output), 'systemGiB': 10, 'source': source, 'factoryVersion': FACTORY_VERSION}, indent=2)+'\n')
        print(f'Installed cloud-init VHDX built and hashed: {manifest}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, pexpect.ExceptionPexpect) as error:
        raise SystemExit(f'VyOS image build failed: {error}') from None
