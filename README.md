# OpenHVX Deployment Lab

Deployment automation for OpenHVX, with two separate layers:

- **Lab**: OpenTofu/KVM provisions Windows machines simulating physical hosts.
- **Platform**: Ansible configures existing Hyper-V hosts and will deploy the
  infrastructure VMs and services on them, for both lab and bare-metal targets.

The three-host Windows/Hyper-V foundation and diskless L2 startup are validated.
The six infrastructure VMs, Ceph, K3s, backend, connector, and Windows agents are
deployed in the lab. See the [platform runbook](docs/lab-platform.md) for access,
verification, recovery, and remaining limits.
See [deployment structure](docs/deployment-structure.md),
[CONTEXT.md](CONTEXT.md), and [detailed status](docs/status.md).

The [VyOS lifecycle](docs/vyos-lifecycle.md) automates its installed image,
owned VM deployment, verification and targeted destruction.

The opt-in [network PoC](docs/network-poc.md) covers logical VPC admission and
a management-only VyOS pool; tenant forwarding remains unimplemented.

## Local setup and validation

From this directory, with `mise` available:

```bash
mise install
mise run bootstrap
mise run check:host
mise run test
```

`bootstrap` installs Python dependencies into `.venv/` and Ansible collections
into `.ansible/`. No system packages are installed automatically.
Diagnostics use the current user's permissions without requiring sudo.
They check KVM, nesting, libvirt connectivity, available RAM, CPU, space under
`/var/lib/libvirt/images`, and IPv4 route conflicts with the chosen CIDR.
Actual resource budgets in the saved plan are checked again before applying it.

## Target topology

The roadmap for distributing the backend across three K3s VMs is documented in
[OpenHVX on K3s](docs/openhvx-k3s.md). The initial lab deployment is described in the [platform runbook](docs/lab-platform.md).

`host_count = 3` creates `lab-hv01`, `lab-hv02`, and `lab-hv03` at
`192.168.50.10`, `.11`, and `.12` with the default CIDR. `vcpu`, `memory`, and
`disk_size` apply **to each host**; diagnostics check their combined requirements.
Default memory is 32 GiB per host (96 GiB total).
The deployed backend runs on three nested Linux K3s VMs, with three separate
Ceph VMs. Windows Failover Clustering and tenant VM HA are not configured. `lab:down` targets all lab hosts.

## Separate entry points

```bash
# Provision Windows hosts in the local KVM lab only
mise run lab:hosts:up

# Configure existing hosts using an explicit inventory and its credentials
PLATFORM_INVENTORY=/absolute/path/to/hosts.yml mise run platform:deploy
PLATFORM_INVENTORY=/absolute/path/to/hosts.yml mise run platform:verify
```

The platform runner does not generate inventory or load lab secrets. Existing
`ansible:configure`, `ansible:bootstrap`, `ansible:rdp`, and `test:lab` commands are
lab adapters that supply the local inventory, secret, and CA.
`platform:verify` currently checks diskless VM startup and deletion on Hyper-V;
it is not yet a full platform acceptance test.

## Automated lab installation

Configure the Windows ISO in `lab.auto.tfvars`. To prepare all three hosts:

```bash
mise run lab:up
```

The task prepares answer ISOs and UEFI media without a keyboard prompt, applies
the plan, waits for WinRM HTTPS, and configures Hyper-V. It installs Windows on
blank disks; the answer file erases disk 0. Do not boot these media against a disk
whose contents must be retained.

Secrets are generated locally under `.lab/`, with access restricted to the QEMU
account. Ansible scripts load them and validate certificates automatically.
To resume after preparation/apply:

```bash
mise run ansible:bootstrap
mise run ansible:configure
```

See [docs/unattended-windows.md](docs/unattended-windows.md) for prerequisites,
Windows edition index, drivers, and diagnostics. `windows:prepare` is also
available separately. Windows update orchestration and Windows Failover Clustering remain separate
workstreams. `lab:up` also runs `lab:platform:up` for the Linux infrastructure and
OpenHVX services.

## Remote Desktop (RDP)

The `windows_rdp` role enables RDP with mandatory NLA and firewall access limited
to the management CIDR. Run it separately with `mise run ansible:rdp`.

On Arch Linux, install a client if needed: `sudo pacman -S remmina freerdp`.
In Remmina, select RDP, address `192.168.50.10`, `.11`, or `.12`, and user
`Administrator`. Paste the secret from `.lab/windows-password` into the Linux
client's password field. The Windows RDP certificate is self-signed; verify and
accept its trust prompt on first connection. Do not disable certificate
validation globally. WinRM certificates are separate.

## Destruction and recovery

`mise run lab:down` displays a destruction plan and asks you to type `lab-hv01`
before applying it. Errors are propagated. Source ISO images are not managed
resources. OpenTofu state and its backups remain on disk.

After a workstation reboot, check libvirt, then run `mise run check:host`.
The lab network and VM have autostart enabled; libvirt service startup depends
on system configuration. Resume with `ansible:bootstrap`, then
`ansible:configure`. A controlled reboot of `lab-hv01` was exercised; the infrastructure VMs restarted.
A complete workstation reboot still needs testing.

Do not version local state, plans, or secrets. Back up
`lab/tofu/environments/lab/terraform.tfstate*` to encrypted local storage before a
risky operation. A shared state backend and automated backups remain to be
addressed. This directory has not yet been initialized as a Git repository.
