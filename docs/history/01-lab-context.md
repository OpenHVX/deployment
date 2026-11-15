# Context — the OpenHVX lab `deployment` repository

**Type:** Historical record

**Status:** Archived; not an operating procedure

**Scope:** Earlier lab decisions and recorded evidence

See the [current documentation index](../index.md) before running commands.

## Updated target — user decision on November 7, 2026

The target is now an HCI Hyper-V IaaS platform with **three hosts**:
`lab-hv01`, `lab-hv02`, and `lab-hv03`, with the OpenHVX backend on the workstation.
This decision supersedes the single-host scope and deferred multi-host work in
the original design below. Nested virtualization capability must be proven
before configuring the cluster.

The foundation provisions three VMs with distinct IP/MAC addresses, each with
8 vCPUs, 32 GiB RAM, and a 200 GiB system disk by default: 24 vCPUs, 96 GiB RAM,
and 600 GiB disk capacity in total. Storage networking, data disks, HCI technology,
quorum, identity, and clustering remain to be defined and implemented.
Three Hyper-V VMs alone do not constitute a functioning HCI platform.
A nested lab on one workstation does not prove physical fault tolerance of the
intended platform.

## Purpose

This file provides initial context to copy into the root of a new repository
named `deployment`. It should let a person or agent build the lab without
rediscovering the decisions recorded here.

The repository must automate a local OpenHVX lab on a powerful workstation.
There is currently no production environment or shared lab. The priority is a
reproducible, disposable, observable environment rather than a highly available
production platform.

## Foundational assumption to verify

The workstation is assumed to be an x86-64 Linux host with KVM/libvirt and a CPU
with nested virtualization extensions enabled. Level-1 Windows Server VMs will
be created on KVM, then run Hyper-V and the level-2 VMs used to test OpenHVX.

This KVM -> Windows Server -> Hyper-V combination is suitable for a lab but must
be treated as experimental. Microsoft documentation primarily describes nested
Hyper-V on a Hyper-V host. The first milestone must therefore prove capability
before developing the rest of the automation.

If the target workstation runs Windows, replace the libvirt implementation:
use Hyper-V as the level-0 hypervisor and expose virtualization extensions to
the level-1 Windows Server VMs. Module interfaces and playbooks must remain
loosely coupled enough to support this replacement.

Before implementation, record:

- Workstation OS and version.
- CPU model/vendor and availability of VT-x/EPT or AMD-V/NPT.
- RAM and SSD capacity actually available to the lab.
- KVM, libvirt, and nested virtualization status.
- A usable bridge/network that will not disrupt workstation networking.

## Desired outcome

Eventually, a command such as `mise run lab:up` must:

1. Check workstation prerequisites.
2. Initialize and apply OpenTofu infrastructure.
3. Wait until Windows is remotely manageable.
4. Configure Windows Server and Hyper-V with Ansible and PowerShell.
5. Deploy the OpenHVX components required by the lab.
6. Run health checks and a nested VM test.

The command must be repeatable. A second run without changes must introduce
neither drift nor unnecessary changes.

## Technical principles

### Mise

`mise` is the sole entry point for repository tools and tasks.

- Declare tools in `.mise.toml` with exact versions or deliberately chosen constraints.
- Version `.mise.toml` and any lock files.
- Keep short tasks in `.mise.toml`; put substantial scripts in `mise/tasks/` or `scripts/`.
- Do not require shell activation: documented commands must work through `mise run ...`.
- Include at least OpenTofu, Python, Ansible, PSRP/WinRM dependencies, SOPS, age,
  jq, and yq. Add Packer if the Windows image build justifies it.
- Do not silently install system packages or modify BIOS/UEFI. Diagnostics must
  explain any commands that require privileges.

Expected tasks:

| Task | Responsibility |
| --- | --- |
| `bootstrap` | Install mise-managed tools and Ansible collections/dependencies |
| `check:host` | Check CPU, KVM/libvirt, nesting, storage, and networking |
| `image:build` | Produce the base Windows image if automated |
| `tofu:init` | Initialize the lab root module |
| `tofu:plan` | Format, validate, and produce a saved plan |
| `tofu:apply` | Explicitly apply the saved plan |
| `ansible:bootstrap` | Establish initial remote administration |
| `ansible:configure` | Apply Windows/Hyper-V/OpenHVX roles |
| `lab:up` | Orchestrate full creation and configuration |
| `lab:down` | Destroy disposable resources with explicit confirmation |
| `test` | Lint, OpenTofu/Ansible/PowerShell validation, and lab tests |

### OpenTofu

OpenTofu owns infrastructure lifecycle:

- Libvirt networks.
- VM pools, volumes, and disks.
- Level-1 Windows Server VMs.
- vCPU, RAM, firmware, interfaces, and exposed CPU capabilities.
- Outputs consumable by Ansible inventory.

The proposed libvirt provider is the community `dmacvicar/libvirt` provider.
Validate compatibility with the selected OpenTofu version and the CPU settings
required by Hyper-V in a minimal spike before creating complex modules.
Explicitly declare every provider source and version constraint.

Version `.terraform.lock.hcl`. Never version `.terraform/`, saved plans, state
files, or state backups.

Local state is acceptable for the initial single-user lab, provided that it is:

- Treated as a secret.
- Backed up to encrypted local storage.
- Never used to inject a permanent password directly into a resource.
- Accompanied by a plan to migrate to an encrypted remote backend with locking
  if the repository becomes shared.

Use modules only when they represent stable responsibilities. Avoid premature
abstraction around a single VM.

### Ansible and PowerShell

Use both with clear boundaries:

- Ansible orchestrates, waits for readiness, applies roles, handles reboots, and
  checks idempotence.
- PowerShell performs native Windows operations: Windows features, Hyper-V,
  vSwitches, WinRM/PSRP, firewall, services, and agent installation.
- Complex PowerShell scripts belong in `powershell/`, are versioned and
  idempotent, and are called through `ansible.windows.win_powershell` or a
  specialized Windows module.
- Do not hide long PowerShell commands inside YAML.

Prefer PSRP or WinRM HTTPS. An HTTP listener restricted to the management network
may serve initial bootstrap, then must be removed or hardened. In a workgroup,
NTLM over HTTPS is acceptable for this lab; do not enable Basic without encryption.
Prefer Kerberos in a domain.

Ansible secrets must come from SOPS/age-encrypted files or environment variables
injected at runtime. Never version plaintext Windows passwords, private
certificates, or OpenHVX tokens.

## Progressive topology

### MVP — required

| Machine | Role | Initial size |
| --- | --- | --- |
| Workstation | KVM/libvirt, OpenTofu, Ansible, development OpenHVX backend | Physical host |
| `lab-hv01` | Windows Server 2022 or 2025, nested Hyper-V, OpenHVX agent | 8 vCPUs, 16–24 GiB, 200 GiB |
| `smoke-l2` | Small disposable VM created in Hyper-V for end-to-end testing | 2 vCPUs, 2–4 GiB, 30 GiB |

All sizes must be validated variables. Default allocations must not exceed the
resources that `check:host` estimates are available.

Initially, the OpenHVX backend stays on the workstation, for example in development
mode or Compose. The `deployment` repository must not copy its source; it
references an image or a configurable working directory.

### Extensions — after MVP validation

- `lab-dc01`: AD DS and DNS if domain/Kerberos scenarios require them.
- `lab-hv02`: a second Hyper-V host for multi-host scenarios.
- Shared iSCSI/SMB storage if clustering scenarios require it.
- A Linux management VM if control-plane isolation becomes useful.
- A Hyper-V cluster only after validating simple single-host operations.

Do not introduce AD, clustering, and shared storage in the first increment: they
multiply failure causes without proving the OpenHVX workflow sooner.

## Networks

Use configurable CIDRs without assuming they are free on the workstation.
Proposed lab values:

- Management: `192.168.50.0/24`, NAT to the Internet for updates.
- Storage: `192.168.51.0/24`, isolated and added only when needed.
- Tenant/fabric networks: internal Hyper-V networks, without a route to the
  workstation LAN by default.

Management addresses must be predictable through DHCP reservations or static IPs.
The workstation must reach PSRP/WinRM, the agent service, and diagnostic endpoints.
Do not expose any of these ports to the Internet.

The MVP uses an internal Hyper-V vSwitch with NAT for nested VMs. Add direct
bridging/MAC spoofing only if a scenario requires it and the physical network
allows it.

## Windows image

The user supplies the Windows Server ISO and license; neither is committed to Git.
The repository may automate a legally obtained evaluation image but must not
bypass activation or redistribute the ISO.

The base image must be reproducible and contain only essentials:

- Unattended installation through `Autounattend.xml`.
- VirtIO drivers required by KVM.
- A temporary bootstrap account with its secret injected at creation.
- PSRP/WinRM or OpenSSH configured on the management network.
- Updates applied according to an explicit policy.
- No OpenHVX agent or environment-specific configuration baked into the image.

Packer is recommended once the build process stabilizes. For the initial spike,
`virt-install` and an answer-file image are acceptable. Do not invest in a golden
image before proving Hyper-V actually starts under KVM on the target workstation.

## Repository structure

The lab provider and the platform deployment have independent lifecycles.
See [deployment structure](../02-deployment-structure.md) for ownership, commands,
and migration details.

```text
deployment/
├── .mise.toml
├── lab/
│   ├── tofu/                 # KVM infrastructure simulating physical hosts
│   ├── windows/              # Unattended Windows installation and bootstrap
│   ├── scripts/
│   └── tests/
├── platform/
│   ├── ansible/              # Shared Hyper-V configuration and future infra VMs
│   ├── powershell/           # Native Hyper-V operations
│   └── kubernetes/           # Future application deployment resources
├── environments/
│   └── lab/hosts.yml         # Inventory contract, generated by the lab
├── scripts/                  # Shared tooling setup and static validation
└── docs/
```

OpenTofu provisions only the simulated hosts on KVM. Ansible configures existing
Windows hosts and will create/configure infrastructure VMs on Hyper-V. The platform
accepts an explicit inventory and never reads libvirt state or `.lab/` secrets.
The lab adapter generates inventory from `tofu output -json` and supplies its
own credentials. Bare-metal deployment supplies inventory and credentials directly.

## Implementation order

### Phase 0 — prove workstation capability

1. Check `/dev/kvm`, libvirt, and the `nested` parameter of `kvm_intel` or `kvm_amd`.
2. Boot a Windows Server VM using host-passthrough CPU and UEFI.
3. Install Hyper-V.
4. Manually create and start a small level-2 VM.
5. Record commands and results in `docs/03-nested-virtualization.md`.

If this fails despite correct CPU settings, suspend the KVM architecture and
evaluate a native Windows/Hyper-V host. Do not hide failures with scripts.

### Phase 1 — reproducible foundation

1. Create `.mise.toml`, diagnostics, and linting.
2. Automate networking, storage, and `lab-hv01` with OpenTofu.
3. Generate Ansible inventory from OpenTofu outputs.
4. Configure Windows and Hyper-V idempotently.
5. Destroy and recreate the lab from scratch.

### Phase 2 — OpenHVX integration

1. Start the OpenHVX backend on the workstation.
2. Install/register the agent on `lab-hv01` without plaintext secrets.
3. Check heartbeat, inventory, and reported capabilities.
4. Execute a simple command, then create/delete `smoke-l2` through OpenHVX.
5. Collect backend, broker, agent, and Windows logs.

### Phase 3 — advanced scenarios

Add a second host, AD/DNS, shared storage, and clustering one component at a time,
each with an acceptance test and destruction procedure.

## Tests and acceptance criteria

The MVP is complete when:

- `mise install` and `mise run bootstrap` work on a clean workstation.
- `mise run check:host` fails early with an actionable message if nesting is missing.
- `tofu fmt -check`, `tofu validate`, and Ansible/PowerShell lint pass.
- Two consecutive post-apply `tofu plan` runs show no changes.
- `lab-hv01` boots and becomes reachable without GUI console intervention.
- Hyper-V is installed and a level-2 VM can start.
- A second Ansible run reports no unexpected changes.
- The OpenHVX agent registers, sends heartbeats, and publishes inventory.
- VM creation, observation, and deletion succeed end to end.
- `mise run lab:down` removes disposable resources without deleting the ISO,
  source images, or a state backup.
- Recovery after workstation reboot is documented and tested.

## Security and safeguards

- No real secrets, ISOs, VM disks, OpenTofu state, or plan artifacts in Git.
- Encrypt declarative secrets with SOPS and age; keep the age key outside the repository.
- Explicitly protect costly-to-rebuild images against accidental destruction
  without making `lab:down` misleading.
- Require confirmation and show targeted resources before any destruction.
- Keep privileged scripts short, audited, and separate from routine tasks.
- Restrict administrative listeners to the management network.
- Do not globally disable Windows Firewall, TLS validation, or libvirt security
  to make tests pass.
- Logs must not print variables marked sensitive.

## Initial exclusions

- Production, actual high availability, and disaster recovery.
- Public exposure of backend or administration interfaces.
- Unauthorized Windows Server download or activation.
- Multiple workstation support before the main lab is stable.
- Kubernetes or a self-hosted CI platform.
- Hyper-V clustering before successful single-host operation.

## Open decisions

Make these decisions after `check:host`; do not assume them in code:

1. Windows Server 2022 or 2025; Server Core or Desktop Experience.
2. Workgroup for the MVP or AD domain from phase 2 onward.
3. RAM, vCPU, and storage capacity actually reservable.
4. Packer image build or initial `virt-install` approach.
5. PSRP/WinRM HTTPS or OpenSSH as the final Ansible transport.
6. OpenHVX backend execution mode and address reachable from `lab-hv01`.
7. Actual need for a second host, clustering, and shared storage.

## Design references

- [Mise configuration](https://mise.jdx.dev/configuration)
- [Mise tasks](https://mise.jdx.dev/tasks/)
- [OpenTofu provider requirements](https://opentofu.org/docs/language/providers/requirements/)
- [OpenTofu dependency lock](https://opentofu.org/docs/language/files/dependency-lock/)
- [Sensitive data in OpenTofu state](https://opentofu.org/docs/language/state/sensitive-data/)
- [Community libvirt provider](https://registry.terraform.io/providers/dmacvicar/libvirt/latest/docs)
- [KVM nested virtualization](https://docs.kernel.org/virt/kvm/x86/running-nested-guests.html)
- [Nested Hyper-V](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/enable-nested-virtualization)
- [Windows administration with Ansible](https://docs.ansible.com/projects/ansible/latest/os_guide/intro_windows.html)
- [WinRM with Ansible](https://docs.ansible.com/projects/ansible/latest/os_guide/windows_winrm.html)

## Implementation tracking — November 7, 2026

This document describes the target, not a completed implementation.
See [docs/status.md](../01-status.md) for the code audit, checks actually performed,
and remaining work. Linux diagnostics are validated; the user still needed to
prove Windows/Hyper-V/L2 capability once an ISO became available at that point.
No lab infrastructure was applied during that audit.

### Unattended installation added

`windows:prepare` prepares installation media for all three hosts, including
drivers and WinRM HTTPS bootstrap. `lab:up` orchestrates this step.
See docs/unattended-windows.md for blank-disk requirements and docs/status.md
for actual observed results.

### Three-host foundation validated

Unattended Windows Server 2025 installation, WinRM HTTPS, Hyper-V, reboots, and
temporary L2 VM startup completed successfully on all three hosts.
`mise run lab:up` now includes `test:lab`.
This proves startup of a diskless L2 VM without a guest OS; it does not complete
OpenHVX/HCI acceptance criteria or guest OS testing. See docs/status.md for limitations.

## Platform deployment update — November 8, 2026

The earlier workstation-backend and Kubernetes-excluded scope is historical.
The lab now has one Ceph VM and one schedulable K3s server VM per Hyper-V host.
Ansible provisions those VMs and configures Ceph, K3s, data services, backend,
connector, and Windows agents. Management VIPs are `.20` for OpenHVX/K3s and `.30`
for the active Ceph Dashboard. Tenant networking remains undecided; Windows
Failover Clustering and tenant VM HA are not configured.

Use [the platform runbook](../05-lab-platform.md) and the latest entries in
[status](../01-status.md) for current commands, evidence, and remaining limits.
