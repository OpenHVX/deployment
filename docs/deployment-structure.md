# Lab and platform deployment boundaries

## Ownership

| Area | Responsibility | Tool |
| --- | --- | --- |
| `lab/tofu/` | KVM networks, disks, and Windows VMs simulating physical hosts | OpenTofu |
| `lab/windows/` | Unattended Windows media, VirtIO drivers, remote bootstrap | Python/PowerShell |
| `lab/scripts/` | Workstation diagnostics, host provisioning, lab credentials/inventory adapter | Shell/Python |
| `platform/ansible/` | Configuration of existing Hyper-V hosts; future infrastructure VM lifecycle and Linux configuration | Ansible |
| `platform/powershell/` | Native Windows/Hyper-V operations shared by lab and bare metal | PowerShell |
| `platform/kubernetes/` | Future OpenHVX application resources | Kubernetes resources or charts |
| `environments/<name>/` | Host inventory and environment-specific platform configuration | Ansible inventory/variables |
| `scripts/` | Shared tooling installation and static checks | Shell |

Infrastructure VMs on Hyper-V will be created and configured using Ansible and
idempotent PowerShell, not a second OpenTofu stack. Define desired state, detect
existing resources, protect data disks, and report changes requiring shutdown.
The initial directory migration did not implement VM provisioning. The subsequent
implementation uses `infra-vms.yml` and `Ensure-InfrastructureVM.ps1`; see the
[platform runbook](lab-platform.md).

## Inventory contract

The platform consumes an existing inventory through `PLATFORM_INVENTORY`. It does
not call OpenTofu, regenerate that inventory, or load credentials from `.lab/`.
Supply normal Ansible connection settings, credentials, and trusted CA configuration
through inventory, protected variable sources, or the execution environment.
Host roles use `management_cidr`; legacy `lab_management_cidr` remains accepted.
There is no default platform inventory, to avoid accidentally targeting the lab.

The lab generates `environments/lab/hosts.yml` from OpenTofu outputs. Its adapter
loads `.lab/windows-password` and `.lab/ca.pem` and passes that inventory to the
same platform runner. The generated inventory retains lab-specific credential
lookups; these are not a requirement for inventories supplied for physical hosts.

```bash
mise run lab:hosts:up
PLATFORM_INVENTORY=/absolute/path/to/hosts.yml mise run platform:deploy
PLATFORM_INVENTORY=/absolute/path/to/hosts.yml mise run platform:verify
```

## Current command behavior

- `lab:hosts:up`: tooling, workstation checks, Windows media, OpenTofu provisioning,
  generated inventory, and authenticated Windows readiness.
- `platform:deploy`: configure Windows baseline, RDP, and Hyper-V on existing hosts.
- `platform:verify`: create/start/delete a temporary diskless Hyper-V VM per host.
- `lab:up`: compose lab host provisioning, shared platform configuration, and verification.
- `lab:down`: destroy simulated hosts through the lab OpenTofu stack, including
  their nested contents; it is not a platform uninstall command for physical hosts.
- `ansible:bootstrap`, `ansible:configure`, `ansible:rdp`, `test:lab`: compatibility
  tasks using the lab adapter and existing generated inventory. They no longer
  regenerate inventory implicitly. Use `inventory:generate` explicitly if needed.

`lab:platform:up` now deploys Ceph/K3s/OpenHVX onto existing lab hosts. `lab:up`
composes host creation, baseline verification, and that platform deployment.
See the [platform runbook](lab-platform.md) for commands and current limits.

## Local state migration on November 8, 2026

The entire `tofu/` directory moved to `lab/tofu/`, including state, provider cache,
lock file, and local variables. Module source relationships and resource addresses
were preserved. Pre-migration state copies are under `.lab/structure-migration/`
with private file permissions. Saved binary plans were invalidated and removed;
run `mise run tofu:plan` before any subsequent apply.

Runtime `.lab/` secrets/media and the source ISO under `images/` stay in place:
absolute paths in local variables and existing VM definitions remain valid.
Only answer templates and the bootstrap source moved to `lab/windows/`.
No VM was stopped, recreated, or modified by this restructuring.

The generated inventory moved from `ansible/inventories/lab/hosts.yml` to
`environments/lab/hosts.yml`. Tooling collections and the Python environment remain
under `.ansible/` and `.venv/`. Do not commit state, generated inventory, or secrets.
