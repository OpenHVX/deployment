# VyOS VM lifecycle

**Type:** Runbook

**Status:** Current; lifecycle acceptance recorded on 2026-11-14

**Scope:** Management-only VyOS VM lifecycle

[Documentation index](index.md)

This workflow owns one management-only VyOS VM per Hyper-V host. It does not
create VPCs, tenant segments, NAT, API credentials or network failover.
Infrastructure deployment remains separate from the Network Orchestrator.

## Prerequisites

Use the pinned workstation tools (`mise install`, `mise run bootstrap`), working
WinRM HTTPS, the existing platform SSH identity and the management switch. The image
factory requires QEMU/KVM, OVMF and media utilities; see the image construction
section. Commands run from the repository root.

## Configuration

| Hyper-V host | VM | Management | MAC | Size |
| --- | --- | --- | --- | --- |
| lab-hv01 | openhvx-vyos-01 | 192.168.50.41/24 | 00:15:5d:48:56:01 | 2 vCPU / 2 GiB / 10 GiB disk |
| lab-hv02 | openhvx-vyos-02 | 192.168.50.42/24 | 00:15:5d:48:56:02 | 2 vCPU / 2 GiB / 10 GiB disk |
| lab-hv03 | openhvx-vyos-03 | 192.168.50.43/24 | 00:15:5d:48:56:03 | 2 vCPU / 2 GiB / 10 GiB disk |

The existing `OpenHVX-Management` switch is required. This workflow never creates
or reconfigures a host uplink. Before creating a stopped/absent guest, the lab
adapter probes its reserved management IP for ICMP/SSH conflicts; this supplements
address reservation and does not prove an address is unused by a silent device.
Each host must have 3 GiB free RAM for the 2 GiB VM plus headroom.

## Procedure

Run these commands from the deployment directory through mise:

```bash
mise run lab:network:vyos-image
mise run lab:network:vyos-up
mise run lab:network:vyos-status
mise run lab:network:vyos-verify
mise run lab:network:vyos-down
```

`vyos-up` builds the image automatically if the default local manifest is missing.
`vyos-down` previews destruction only; it prints the deployment UUID and exact
host/VM/disk identities. To apply that specific destruction:

```bash
mise exec -- python lab/scripts/vyos-down.py --apply --confirm DEPLOYMENT_UUID
```

For a single host, use the underlying command with `--host`:

```bash
mise exec -- python lab/scripts/vyos-up.py --host lab-hv01
mise exec -- python lab/scripts/vyos-status.py --host lab-hv01
mise exec -- python lab/scripts/verify-vyos.py --host lab-hv01
mise exec -- python lab/scripts/vyos-down.py --host lab-hv01
mise exec -- python lab/scripts/vyos-down.py --host lab-hv01 --apply --confirm DEPLOYMENT_UUID
```

## Image construction

`environments/lab/network/vyos-iso.json` pins the exact official rolling ISO and
SHA256 from the GitHub release API, plus the official VyOS cloud-init package and
its repository SHA256. The selected rolling build is for this lab, not a production
release policy. Updating the source is an explicit maintenance action.

`image-builds/vyos/build.py` downloads and hashes those artifacts, then runs an isolated
QEMU/KVM guest using disposable files under `.lab/network/image-build`. It invokes
the VyOS installer on that guest's only 10 GiB virtual disk. No workstation block
device is exposed to QEMU and no privileged mount or system package installation
is used. OVMF supplies UEFI firmware. Supply `--firmware`/`--firmware-vars` if the
workstation uses different paths.

The installed guest receives the pinned VyOS cloud-init package and its dependencies
from signed Debian repositories. The factory enables only NoCloud (no default-user fallback datasource), locks the default
VyOS password, removes builder-specific Ethernet identity/configuration, generated
SSH host keys and cloud instance state, powers
off the guest, then converts its installed disk to VHDX. A random temporary installer
password is never logged or served and is discarded after the account is locked.
Debian dependency versions are selected by apt; the entire build is not bit-for-bit
reproducible. The resulting image is identified by its own SHA256.

The accepted image manifest is `.lab/network/image.json`. A verified existing
image is reused. A partial builder requires an explicit `--rebuild`; that flag
replaces only the tool's disposable QEMU disk. Existing Hyper-V VMs are never
upgraded/replaced by rebuilding an image.

```bash
mise exec -- python image-builds/vyos/build.py --rebuild
```

`VYOS_IMAGE_MANIFEST=/absolute/path/to/manifest.json` can select a separately built,
verified installed image. Use `environments/lab/network/vyos.example.json` as its
contract. The initial cloud-init/SSH behavior must be compatible with the verifier.

## Ownership and repeatability

The local `.lab/network/deployment-id` UUID is stable. Generated declarations live
in `.lab/network/windows-vars.yml`. Protect and retain these files; losing them is
not permission to adopt existing VMs.

Each host stores a marker in `C:\OpenHVX\Network\openhvx-vyos-NN\managed.json`,
including deployment UUID, VM GUID, host, image/seed hashes, MAC and hardware
specification. The VM annotation repeats the deployment identity and role.
Successful reruns verify those identities and hardware instead of replacing disks.
A changed declaration or unowned existing VM/directory is rejected.

Destruction checks the marker and VM GUID, annotation, expected disk path, snapshots,
other disk attachments and reparse points before mutation. It stops the selected
owned VM, removes its definition, system disk and bootstrap seed, then removes only
empty owned directories. Unexpected files are retained for inspection. Shared image
caches, switches, agents, backend, Ceph and other VMs are retained.

An interruption between VM creation and recording its identity, a partial hardware
configuration, or unknown files can require operator inspection. The workflow does
not silently adopt/reinstall uncertain resources. Destroying an owned partial
preparation is possible only when its identity and attachment checks are conclusive.

## Verification

The build console is `.lab/network/image-build/build.log`. `vyos-status` reads the
hosts through verified WinRM and prints their VM GUID/state, also recording
`.lab/network/instances/*.json`.

The verifier connects with the existing platform public-key identity. First SSH
trust is TOFU on the private lab network, pinned in `.lab/network/known_hosts` under
the VM GUID read through WinRM. A recreated VM gets a new alias; a changed key for
the same VM GUID is rejected. This is not hardware-backed attestation.

Verification checks cloud-init completion, expected hostname and exact image
version, management MAC and locked password state. It writes
`.lab/network/verify-result.json`. Bootstrap media contain the public key, never
private SSH keys or provider API secrets. The temporary media server exposes only
verified OS media and public bootstrap seeds on the lab management address.

## Recorded acceptance

On 2026-11-14, the full three-host deploy/destroy/recreate cycle passed, including no-change
reruns and wrong-owner refusal. The final state leaves all three instances running
and verified over SSH. `.lab/network/lifecycle-result.json` records image identity,
final VM GUIDs and the acceptance checks. Detailed evidence includes
`idempotence-final.log`, `ownership-rejection.log`, `destroy.log`,
`destroy-again.log`, `absent-status.log`, `recreate.log` and `static-checks.log`.
These are acceptance records; use `vyos-status` for current live state.

## Recovery and limitations

Inspect ownership receipts and the selected VM before retrying a partial operation.
Do not regenerate the deployment UUID or adopt an existing unowned VM. Rebuilding
an image does not upgrade existing routers. Hardware resizing requires a separate
maintenance workflow. Tenant routing, VyOS HTTP API configuration and router
failover are outside this procedure.

## Related documents

- [Network PoC](07-network-poc.md)
- [Repository structure](02-deployment-structure.md)
- [Current status](01-status.md)
