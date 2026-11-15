# Current deployment status

**Type:** Status

**Status:** Recorded state as of 2026-11-15; not a live health report

**Scope:** Nested lab infrastructure and network PoC

[Documentation index](index.md)

## Implemented capabilities

| Component | Implemented behavior | Verification scope |
| --- | --- | --- |
| Windows/Hyper-V | Three simulated hosts, unattended installation, WinRM HTTPS and Hyper-V configuration | Historical foundation checks; temporary nested VM startup/deletion |
| Linux infrastructure | Three K3s VMs and three Ceph VMs, independent of tenant infrastructure | Lab platform acceptance recorded in the implementation history |
| OpenHVX platform | Replicated backend, MongoDB/RabbitMQ, Windows agents and Ceph connector | API/task and storage checks described in the lab runbook |
| Logical networking | VPC admission, quotas, durable command/result transport and planning journal | Planning roundtrip recorded on 2026-11-14 |
| VyOS lifecycle | Image construction, owned VM creation, inspection, verification and targeted destruction | Three-host deploy/destroy/recreate acceptance recorded on 2026-11-14 |
| Deployment structure | Versioned inventory/placement, component roles, explicit Kubernetes YAML and Kustomize release configuration | Offline refactor checks on 2026-11-15; no deployment performed |

## Refactor verification on 2026-11-15

The refactor passed 13 offline contract tests, OpenTofu formatting/validation and
all Ansible playbook syntax checks. Extracted component tasks were checked with
`--list-tasks`. The declared inventory matched OpenTofu outputs.

The legacy and new Kubernetes renderers produced 32 equivalent resources after
normalizing Secret encoding, including PVCs, selectors and rollout checksums.
Protected credentials, ownership declarations and state hashes were unchanged;
native PowerShell operations were unchanged.

Refreshed OpenTofu plans before and after the refactor were identical. Both show
existing libvirt interface-address drift on three Windows domains, with no resource
replacement. No apply or live lifecycle acceptance was performed during this check.
Private evidence is under `.lab/refactor-2026-11-15/`, including `validation.txt`,
`checks.log` and the saved comparison plans.

## Limitations

- Network Orchestrator executes planning only. VyOS API access, provider effects,
  subnets/IPAM, tenant NIC configuration, NAT and network failover are unimplemented.
- Three router VMs do not establish tenant network HA.
- The single-workstation lab does not establish production failure tolerance.
- Ceph initiator multipathing, tenant VM HA and Windows Failover Clustering remain separate work.
- Shared state storage, an external image registry and production credential/network hardening remain separate work.

## Verification and evidence

Use the [lab deployment runbook](05-lab-platform.md) for present platform checks,
[VyOS lifecycle](06-vyos-lifecycle.md) for router checks and
[network PoC](07-network-poc.md) for planning checks. These procedures have different
side effects; acceptance tests may create and clean up disposable resources.

Earlier acceptance details are preserved in the
[implementation history](history/02-lab-status-2026-11-14.md). Historical observations
are not a substitute for current inspection.
