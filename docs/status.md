# Status verified on November 7, 2026

## VyOS VM lifecycle — November 14, 2026

The deployment now builds an installed UEFI/cloud-init VyOS VHDX from the pinned
official `2026.11.14-0016-rolling` ISO and pinned official cloud-init package.
The image factory is QEMU/KVM-based and runs without privileged workstation mounts.
The generated image manifest is `.lab/network/image.json` (factory version 3).

One management-only VyOS runs on each Hyper-V host at `192.168.50.41`, `.42`, and
`.43`, with 2 vCPUs, 2 GiB RAM and a 10 GiB system disk. SSH public-key access,
exact version, cloud-init completion, expected MAC and unusable password credentials
were verified on all three. Tenant networking and the VyOS HTTP API are not configured.

Real lab acceptance passed:

- Deployment, followed by a second run with `changed=0` on all hosts.
- Wrong deployment owner rejected before mutation (`changed=0`).
- Targeted destruction of all three VM definitions and system disks.
- Repeated destruction with `changed=0`; all VM/disk states proved absent.
- Recreation with new VM GUIDs and successful guest verification on all three.
- Other VM names, GUIDs and running states matched their pre-test baseline.
- Static checks: 13 Python tests, OpenTofu formatting/validation and all Ansible
  playbook syntax checks. The lifecycle PowerShell scripts also executed natively.

Evidence is `.lab/network/lifecycle-result.json`, with detailed logs and instance
records under `.lab/network/`. The final state leaves all three VyOS VMs deployed.
See [VyOS lifecycle](vyos-lifecycle.md) for commands, ownership boundaries and image
maintenance. Earlier entries below retain their historical image prerequisites.

## Network Orchestrator planning — November 14, 2026

A separate TypeScript Network Orchestrator now runs as three ready K3s replicas.
The controller atomically creates a network command/outbox with each new logical
VPC. The worker persists command identity and its result/outbox in its separate
`openhvx-network` MongoDB database, then publishes a stable planning result.
The controller validates and stores that observation without marking the VPC ready.

`mise run lab:network:verify` passed with asynchronous planning through the public
TLS API, real RabbitMQ and the deployed executor. Test VPCs and tenant were removed.
The acceptance evidence records `planningRoundtrip: true` in
`.lab/infra/network-result.json`. Controller and gateway were rolled out with the
worker; unrelated application images and host/router configuration were retained.

Backend tests passed, including a cross-process executor restart and late-result
cancellation test against temporary MongoDB replica sets. The dedicated transport
test also passed against lab RabbitMQ over trusted TLS in an isolated temporary
vhost; that vhost was deleted after the test. The optional network Compose profile,
Kubernetes renderer and Ansible playbooks passed their configuration checks.

This implements `network.vpc.plan` only. Provider effects, VyOS access, router
ownership/fencing, subnets, IPAM, host NIC commands, NAT and network failover are
not implemented by this worker. Old planned VPCs can request a first plan through
`POST .../network/vpcs/{id}/plan`. See the backend's `docs/network-orchestrator.md`.

## Network control-plane PoC — November 14, 2026

The backend `feature/op/network` controller/gateway increment was deployed to
all three K3s nodes using `mise run lab:network:deploy`. Both deployments rolled
out successfully with three replicas. Other application images were retained.

`mise run lab:network:verify` passed through the public TLS/admin API: logical VPC
creation, replay, changed-body rejection, overlapping CIDRs, quota enforcement,
limit reduction, tenant deletion protection and cleanup. The acceptance resources
were removed. Evidence is `.lab/infra/network-result.json`.

The VPC API is opt-in and creates `planned` logical resources only. No VyOS VM
was created and no tenant traffic configuration changed. The management bootstrap
automation and three-router plan are prepared; an installed, verified
cloud-init-capable VyOS VHDX is still required. Generic public nightly ISO media
is not substituted for that image. Forwarding, subnet/NIC realization, NAT and HA
remain subsequent increments. See [network PoC](network-poc.md).

Static deployment validation passed: 11 Python tests, OpenTofu formatting and
validation, and all Ansible playbook syntax checks. Backend unit and integration
tests passed; real RabbitMQ integration was skipped without its test URL.

The general platform smoke initially failed because all Windows agents were
stopped with old November 9 heartbeats. Read-only inspection found failed AMQP
startup attempts and no running agent processes. After confirming AMQPS was
reachable from each Hyper-V host, their existing scheduled tasks were started
without replacing binaries, configuration or journals. All three agents returned
online. `mise run lab:platform:verify` then passed (including replay of its
previously completed echo task, rather than a fresh compute execution). Startup
recovery after infrastructure unavailability still needs hardening.

The sections below retain historical progress and limitations.

## Foundation audit

This directory contains scaffolding, not a completed MVP. It has no `.git`
directory; no commits have been created. `CONTEXT.md` remains the target specification.

Completed fixes:

- Pinned libvirt provider to 0.8.3, corrected network/VM schemas, and updated lock.
  Reference: https://github.com/dmacvicar/terraform-provider-libvirt/tree/v0.8.3/website/docs/r
- Configured host-passthrough CPU, Q35, UEFI, and attached disk/ISO.
- Parameterized CIDR and sizing with validation; resource and route checks run
  before planning and against actual plan values.
- Generated secret-free inventory from outputs; TLS validation enabled.
- Waited for WinRM from the controller; installed Hyper-V with reboot and vmms.
- Installed WinRM/PSRP dependencies; loaded Ansible configuration explicitly.
- Removed false-positive destruction/test results; displayed destruction plan
  and required confirmation of targeted resources.
- Removed fixed password from answer template; corrected UEFI partitions.

## Checks performed

- `mise install`, `mise run bootstrap`: passed on this workstation.
- `mise run check:host`: passed without root.
- `mise run test`: Bash syntax, three generator tests, recursive formatting and
  OpenTofu validation, syntax of both Ansible playbooks.
- These do not replace ansible-lint, PSScriptAnalyzer/Pester, idempotence tests,
  or acceptance tests on a real lab.
- No `tofu apply`, destruction, or changes to the workstation's five existing VMs.

## Agreed next step at that time

The user did not yet have a Windows ISO and would run the Windows/Hyper-V test.
Record results in `nested-virtualization.md`. Do not present the automation as
validated before that test.

Remaining work after proving capability:

1. Reproducible Windows image build, drivers, temporary secret, HTTPS listener,
   and update policy.
2. Internal vSwitch/NAT and L2 guest OS test.
3. Backend installation from a configurable neighboring repository, agent,
   secrets, registration, heartbeat, and inventory.
4. Create/observe/delete through OpenHVX and collect logs.
5. Full recreation, two drift-free plans, second Ansible run, controlled
   destruction, and recovery after reboot.
6. Ansible/PowerShell lint and encrypted state backup.

Do not add AD, clustering, or shared storage before single-host validation.

## Resuming after the ISO was supplied

The Windows ISO is now supplied at `images/WindowsServer.iso`; local variables
come from `lab.auto.tfvars`. An initial apply created the network, pool, and disk,
then failed on the Q35-incompatible IDE ISO drive. The module now transforms
CD-ROM XML to SATA; a test covers two drives and preservation of the VirtIO disk.
Resuming created only `lab-hv01` (one addition, no replacement/deletion).
The VM boots and inventory is generated. Windows installation, Hyper-V, and L2
were still pending; capability had not yet been proven.
The XML test requires `xsltproc` (Arch Linux system package libxslt).

## User-requested deletion

The six VMs visible on qemu:///system were deleted with their disks, including
specific dev-* and postgres-dev base images and its cloud-init ISO.
The source Windows ISO, libvirt networks, and pools were retained.
Lab state was refreshed; saved plan and inventory were invalidated.
Resume with tofu:plan then tofu:apply to recreate lab-hv01.

## Updated target: three IaaS/HCI hosts

At the user's request, the target changed to three Hyper-V hosts, with OpenHVX
backend on the workstation. OpenTofu uses host_count (default 3), addresses
.10/.11/.12, and three distinct MACs. A module-address migration preserves
lab-hv01 when single-host state exists. Checks cover aggregate resources.
Inventory exports all hosts; playbooks target all three.
No creation was run as part of this change; the plan was prepared.
Distributed storage, storage networks/disks, quorum, identity, and clustering
remain undefined. This decision supersedes historical single-host priorities;
Windows/Hyper-V capability was still unproven at that point.

## Automated Windows installation

Unattended preparation is implemented: UEFI media without keyboard prompt,
per-host answers, VirtIO drivers, local secret, certificates, and WinRM HTTPS
bootstrap during specialize. `lab:up` includes windows:prepare; Ansible loads the
secret and CA automatically. Six static tests pass, including XML rendering.
All three VM definitions were replaced to attach media; disks were preserved.
The first unattended boot reached Windows installation (10% observed on lab-hv01).
Final Windows, WinRM, and Hyper-V success was still pending at this stage.
See unattended-windows.md; earlier references to non-automated imaging describe
the historical state before this implementation.

### Actual unattended installation results

- Three Windows Server 2025 installations without keyboard input or GUI navigation.
- Bootstrap fixed for pnputil code 259 (“drivers already present”), with explicit
  viostor/NetKVM device-state checks.
- Initial bootstrap repaired using NTLM with message encryption, followed by
  WinRM HTTPS validation on all three hosts; HTTP removed.
- Answer ISOs regenerated with the fix for future deployments.
- Hyper-V installation, reboot, and vmms service: successful on all three.
- `test:lab`: temporary L2 VM start/deletion successful on all three.
- Post-apply OpenTofu plan: no changes.
- Static checks: six Python tests, Bash syntax, OpenTofu validation, three playbooks.
- Local logs under `.lab/logs/` (not versioned).

HCI is not complete: distributed storage, storage networking, quorum/identity,
clustering, backend, and OpenHVX agent remain to be implemented.

Second Ansible run completed: `changed=0`, `failed=0`, `unreachable=0` on all
three hosts; no additional reboot. Log: `.lab/logs/idempotence.log`.

## RDP access

The windows_rdp role enables Remote Desktop with NLA and a TCP/3389 rule limited
to the management CIDR. Built-in RemoteDesktop rules are disabled to avoid wider
exposure. The role is part of normal configuration and can also run separately
with `mise run ansible:rdp`.

RDP configuration succeeded on all three hosts: no failures, port 3389 reachable
from the workstation. Static checks passed; the agent did not open a graphical
RDP session. Local log: `.lab/logs/rdp.log`.

## Memory increased to 32 GiB per host

Local configuration, default, and example changed to 32768 MiB, totaling 96 GiB
for three hosts. VMs were shut down cleanly; maximum and current memory were
increased offline through libvirt, then the VMs restarted. OpenTofu state was
refreshed to avoid forced domain-definition replacement: the final plan shows
no changes. Windows disks and definitions were preserved.
