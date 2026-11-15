#!/usr/bin/env python3
"""Build private per-host unattended media, without modifying existing VMs."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
NS = 'urn:schemas-microsoft-com:unattend'
WCM = 'http://schemas.microsoft.com/WMIConfig/2002/State'
ET.register_namespace('', NS)
ET.register_namespace('wcm', WCM)
def element(parent, tag, text=None, **attrs):
    node = ET.SubElement(parent, '{'+NS+'}'+tag, attrs)
    if text is not None: node.text = str(text)
    return node

def component(settings, name):
    return element(settings, 'component', name=name, processorArchitecture='amd64',
                   publicKeyToken='31bf3856ad364e35', language='neutral', versionScope='nonSxS')

def answer(name, password, index):
    tree = ET.parse(ROOT / 'lab/windows/answer-files/autounattend.xml')
    root = tree.getroot()
    root.find('.//{'+NS+'}AdministratorPassword/{'+NS+'}Value').text = password
    osimage = root.find('.//{'+NS+'}OSImage')
    install = element(osimage, 'InstallFrom')
    metadata = element(install, 'MetaData', **{'{'+WCM+'}action':'add'})
    element(metadata, 'Key', '/IMAGE/INDEX'); element(metadata, 'Value', index)
    element(osimage, 'WillShowUI', 'OnError')
    specialize = element(root, 'settings', **{'pass':'specialize'})
    shell = component(specialize, 'Microsoft-Windows-Shell-Setup')
    element(shell, 'ComputerName', name)
    deployment = component(specialize, 'Microsoft-Windows-Deployment')
    run = element(deployment, 'RunSynchronous')
    cmd = element(run, 'RunSynchronousCommand', **{'{'+WCM+'}action':'add'})
    element(cmd, 'Order', 1)
    # Discover the seed DVD without assuming its drive letter.
    command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"$p = Get-Volume | Where-Object FileSystemLabel -eq 'HVXSEED' | Select-Object -First 1; if (!$p) { exit 1 }; & ($p.DriveLetter + ':\\Initialize-LabWindows.ps1')\""
    element(cmd, 'Path', command)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)

def run(*args, **kw):
    return subprocess.run([str(a) for a in args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)

def main():
    os.chdir(ROOT)
    os.umask(0o077)
    for tool in ('tofu', 'openssl', '7z', 'xorriso', 'setfacl', 'curl'):
        if not shutil.which(tool): raise SystemExit(f'Outil système requis : {tool}')
    # Evaluate the actual HCL configuration; no ad-hoc parsing of tfvars.
    expression = 'jsonencode({ hosts = local.hyperv_hosts, cidr = var.management_cidr, iso = var.os_iso_path })'
    result = run('tofu', '-chdir=tofu/environments/lab', 'console', '-no-color', '-var=host_seed_iso_paths={}', input=(expression+'\n').encode())
    config = json.loads(json.loads(result.stdout.decode().strip()))
    private = ROOT / '.lab'
    private.mkdir(mode=0o700, exist_ok=True)
    password_file = private / 'windows-password'
    supplied = os.environ.get('LAB_WINDOWS_PASSWORD')
    if supplied and password_file.exists() and password_file.read_text().strip() != supplied:
        raise SystemExit('LAB_WINDOWS_PASSWORD diffère du secret local : retirer cette variable pour reprendre le lab existant.')
    if not password_file.exists(): password_file.write_text(supplied or secrets.token_urlsafe(30)+'aA1!')
    password = password_file.read_text().strip()
    if len(password) < 16: raise SystemExit('Le secret local doit contenir au moins 16 caractères.')
    ca_key, ca = private/'ca.key', private/'ca.pem'
    if not ca.exists():
        run('openssl','req','-x509','-newkey','rsa:3072','-nodes','-keyout',ca_key,'-out',ca,
            '-days','365','-subj','/CN=OpenHVX Lab CA','-addext','basicConstraints=critical,CA:TRUE')
    # Use a user-supplied VirtIO ISO or download Fedora's stable distribution once.
    virtio = Path(os.environ.get('LAB_VIRTIO_ISO', str(private/'virtio-win.iso'))).resolve()
    if not virtio.exists():
        print('Téléchargement des pilotes VirtIO depuis Fedora…', flush=True)
        temporary = virtio.with_suffix('.download')
        run('curl','--fail','--location','--retry','3','--output',temporary,
            'https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso')
        temporary.replace(virtio)
    edition = os.environ.get('LAB_VIRTIO_WINDOWS_VERSION','2k25')
    index = int(os.environ.get('LAB_WINDOWS_IMAGE_INDEX','4'))
    if index < 1: raise SystemExit('Index image invalide')
    # QEMU may read seed media, while other local users may not read credentials.
    qemu_user = os.environ.get('LAB_QEMU_USER', 'libvirt-qemu')
    run('setfacl','-m',f'u:{qemu_user}:--x',private)
    media = private/'media'
    media.mkdir(mode=0o700,exist_ok=True)
    run('setfacl','-m',f'u:{qemu_user}:--x',media)
    seeds = {}
    with tempfile.TemporaryDirectory(dir=private) as tmp:
        tmp = Path(tmp)
        drivers = tmp/'drivers'; drivers.mkdir()
        for driver in ('viostor', 'NetKVM'):
            run('7z','x',virtio,f'{driver}/{edition}/amd64/*',f'-o{drivers}','-y')
            if not list((drivers/driver/edition/'amd64').glob('*.inf')):
                raise SystemExit(f'Pilotes {driver}/{edition}/amd64 absents de {virtio}')
        for name, host in sorted(config['hosts'].items()):
            ipaddress.ip_address(host['ip'])
            seed = media/(name+'.iso')
            # Stable media on rerun; rebuild explicitly only while VMs are off.
            manifest = {'ip':host['ip'],'cidr':config['cidr'],'index':index,'version':edition,
                        'password':hashlib.sha256(password.encode()).hexdigest(),
                        'bootstrap':hashlib.sha256((ROOT/'lab/windows/Initialize-LabWindows.ps1').read_bytes()).hexdigest(),
                        'template':hashlib.sha256((ROOT/'lab/windows/answer-files/autounattend.xml').read_bytes()).hexdigest()}
            record = media/(name+'.json')
            if seed.exists():
                if not record.exists() or json.loads(record.read_text()) != manifest:
                    raise SystemExit(f'Média {name} existant différent : arrêter les VM et retirer son ISO/manifest local avant reconstruction.')
                seeds[name] = str(seed); continue
            folder = tmp/name; folder.mkdir()
            (folder/'Autounattend.xml').write_bytes(answer(name,password,index))
            shutil.copytree(drivers,folder/'$WinPEDriver$')
            shutil.copy(ROOT/'lab/windows/Initialize-LabWindows.ps1',folder)
            ext = folder/'server.ext'
            ext.write_text(f'subjectAltName=IP:{host["ip"]},DNS:{name}\nextendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n')
            run('openssl','req','-newkey','rsa:2048','-nodes','-keyout',folder/'server.key','-out',folder/'server.csr','-subj',f'/CN={name}')
            run('openssl','x509','-req','-in',folder/'server.csr','-CA',ca,'-CAkey',ca_key,'-set_serial',str(secrets.randbits(128)),
                '-out',folder/'server.pem','-days','365','-extfile',ext)
            pfx_password = secrets.token_urlsafe(24)
            env = dict(os.environ, HVX_PFX_PASSWORD=pfx_password)
            run('openssl','pkcs12','-export','-legacy','-inkey',folder/'server.key','-in',folder/'server.pem',
                '-out',folder/'server.pfx','-passout','env:HVX_PFX_PASSWORD',env=env)
            run('openssl','x509','-in',ca,'-outform','DER','-out',folder/'ca.cer')
            for item in ('server.key','server.csr','server.pem','server.ext'): (folder/item).unlink()
            (folder/'host.json').write_text(json.dumps({'management_cidr':config['cidr'],'pfx_password':pfx_password}))
            run('xorriso','-as','mkisofs','-quiet','-J','-r','-V','HVXSEED','-o',seed,folder)
            run('setfacl','-m',f'u:{qemu_user}:r--',seed)
            record.write_text(json.dumps(manifest,sort_keys=True))
            seeds[name] = str(seed)
    # A dedicated UEFI-only installation ISO removes "Press any key to boot".
    auto_iso = media/'WindowsServer-auto.iso'
    source = Path(config['iso'])
    previous = media/'windows-source.json'
    if source == auto_iso and previous.exists():
        source = Path(json.loads(previous.read_text())['source'])
    fingerprint = {'source':str(source),'size':source.stat().st_size,'mtime':source.stat().st_mtime_ns}
    stamp = media/'windows-source.json'
    if auto_iso.exists() and (not stamp.exists() or json.loads(stamp.read_text()) != fingerprint):
        raise SystemExit('ISO Windows source modifiée : supprimer explicitement le média automatique hors utilisation avant reconstruction.')
    if not auto_iso.exists():
        print('Préparation du média UEFI sans invite clavier…', flush=True)
        with tempfile.TemporaryDirectory(dir=private) as tmp:
            run('7z','x',source,f'-o{tmp}','-y')
            boot = 'efi/microsoft/boot/efisys_noprompt.bin'
            if not (Path(tmp)/boot).exists(): raise SystemExit('Boot UEFI noprompt absent de cette ISO')
            run('xorriso','-as','mkisofs','-quiet','-iso-level','3','-J','-joliet-long','-r','-V','WIN_AUTO',
                '-e',boot,'-no-emul-boot','-o',auto_iso,tmp)
        run('setfacl','-m',f'u:{qemu_user}:r--',auto_iso)
        stamp.write_text(json.dumps(fingerprint))
    override = ROOT/'tofu/environments/lab/zz-unattended.auto.tfvars.json'
    override.write_text(json.dumps({'host_seed_iso_paths':seeds,'os_iso_path':str(auto_iso)},indent=2)+'\n')
    print('Médias prêts. Secret dans .lab/windows-password ; CA dans .lab/ca.pem. Aucune VM effacée ou redémarrée.')

if __name__ == '__main__':
    try: main()
    except subprocess.CalledProcessError as exc:
        # Avoid printing command arguments or stdout containing credentials.
        raise SystemExit('Préparation échouée : '+exc.stderr.decode(errors='replace')[-1500:])
