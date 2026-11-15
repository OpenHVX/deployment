# Deployment structure

**Type:** Reference

**Status:** Current

**Scope:** Repository ownership, configuration and deployment boundaries

[Documentation index](index.md)

This repository owns the infrastructure required to run OpenHVX. OpenHVX remains
the source of truth for tenants, VPCs and tenant resources. Deployment provisions
the management infrastructure; it does not create a parallel tenant inventory.

## Where to make a change

| Directory | Responsibility |
| --- | --- |
| `environments/lab/inventory.yml` | Declared Hyper-V management hosts |
| `environments/lab/host_vars/` | Infrastructure VM placement, addresses, disks and VyOS sizing |
| `environments/lab/group_vars/` | Ansible connection policy; credentials are environment lookups |
| `tofu/environments/lab/` | KVM lab hosts and management network; local `.tfvars` supplies workstation paths |
| `tofu/modules/` | Libvirt network and Windows VM resources |
| `ansible/playbooks/` | Execution order and target groups |
| `ansible/roles/` | Component configuration and lifecycle tasks |
| `ansible/powershell/` | Native Windows and Hyper-V operations, including ownership checks |
| `image-builds/vyos/` | Installed VyOS image factory; pinned input catalog is in `environments/lab/network/` |
| `kubernetes/base/` | Explicit workload, service, storage and ingress YAML |
| `kubernetes/overlays/lab/` | Declared application image versions and lab registration/network policy |
| `kubernetes/overlays/lab/private/` | Credential templates, without credential values |
| `kubernetes/operations/` | Explicit operator preflight/recovery tools |
| `lab/windows/`, `lab/scripts/` | Workstation media preparation, lab adapters and acceptance tools |
| `scripts/` | Shared Ansible entry point, tooling and static validation |
| `tests/` | Offline contract tests |

A playbook selects the hosts and imports a role's named task file. Component
behavior belongs in that role. PowerShell keeps the operations that require native
Hyper-V APIs. There is no custom provisioning framework between these tools.

The OpenTofu stack still derives simulated host addresses from its CIDR and host
count. `inventory:generate` checks its outputs against the declared inventory and
fails on disagreement. Resolve the difference explicitly before configuring hosts.
The current VyOS lifecycle supports 2 CPUs and 2 GiB per router; other sizing is
rejected until a maintenance workflow exists. Linux connection inventory and media manifests are derived from the versioned VM
declarations; they are not independent configuration inputs to edit by hand.

## Configuration, secrets and state

Version desired configuration in the directories above. Keep `.lab/` private:

- `.lab/infra/`: credentials, SSH identity, generated Linux inventory, seeds, build
  artifacts, deployment output and acceptance reports.
- `.lab/network/`: deployment UUID, ownership declarations, guest SSH trust,
  verified image receipts and lifecycle evidence.
- `.lab/windows-password`, `.lab/ca.pem`: local credentials and trust material.

`tofu/environments/lab/terraform.tfstate*` records resource identities. Back it up
to encrypted storage. State, plans, generated media, `.lab/`, `.venv/` and
`.ansible/` are ignored by Git. A shared state backend remains future work.

Do not regenerate secrets or ownership UUIDs to repair a failed deployment.
Inspect the existing state and receipts first. Destruction validates the VM GUID,
notes, deployment UUID and attached disks before deleting owned resources.

## Build, review, apply

```bash
# Offline checks: no host configuration or application deployment
mise run test
mise run lab:network:plan
mise run kubernetes:inspect

# Render credentials privately, without applying anything
mise run kubernetes:render
# Output: .lab/infra/openhvx.yml, mode 0600. Do not paste it into tickets/logs.
```

`kubernetes:inspect` displays public resources and image versions. Secret resources
are completed only by the private renderer. That renderer fills explicit templates
and adds configuration checksums, then calls Kustomize; it does not define workloads
in Python. Registration and network flags come from `settings.yml`, and image tags
come from `kustomization.yaml`. Old `.lab/infra/image-overrides.json`,
`network-settings.json` and `bootstrap-complete` files no longer control rendering.
They can remain as historical evidence.

For a new lab, provision the Windows hosts, then `mise run lab:infrastructure:up`
to prepare Linux VMs, K3s and Ceph. Build/import application images with
`mise run lab:images:build`. The command prints a content-derived tag; it does not
change the declared release. Review and set the desired tags in
`kubernetes/overlays/lab/kustomization.yaml`, then run `mise run lab:platform:up`.
An existing lab can deploy its already imported declared images directly.

For the first administrator only, explicitly enable `register_enabled: "true"`
before deployment. After creating the administrator, set it back to `"false"`
and apply again. Registration is no longer changed by a hidden marker file.
`lab:up` composes provisioning and application deployment; on a fresh lab use the
staged workflow above to prepare and promote images first.

`mise run lab:network:deploy` renders and applies the declared controller, gateway
and executor resources through Ansible, after verifying there are no unresolved
tasks. It neither builds images nor patches image tags through SSH. VyOS lifecycle
commands remain separate; the current executor is plan-only.

## Other environments

```bash
PLATFORM_INVENTORY=/absolute/path/to/inventory.yml mise run platform:deploy
PLATFORM_INVENTORY=/absolute/path/to/inventory.yml mise run platform:verify
```

The shared runner requires an explicit inventory and does not load lab credentials.
Lab adapters supply the versioned lab inventory, local password and trusted CA.
The `ansible:configure` and `ansible:rdp` tasks configure existing lab hosts;
`platform:verify` tests temporary diskless Hyper-V VM startup/deletion.

## Migration on November 15, 2026

The local branch is `refactor/deployment-structure`. The baseline commit precedes
this migration. Whole directories moved, including ignored OpenTofu state and
provider caches. Resource addresses, module relationships and ownership IDs did
not change. Runtime paths under `.lab/` and source media under `images/` stayed in
place. Previous saved plans were moved into `.lab/refactor-2026-11-15/`; generate a
fresh plan before applying. No apply is part of this migration.

Private pre-migration state, file hashes and renderer are under
`.lab/refactor-2026-11-15/`. The legacy/new rendering comparison normalizes Secret
encoding and checks every resource, including rollout checksums, selectors and
PVC definitions. Static validation does not replace a subsequent controlled lab
acceptance run.

The refreshed OpenTofu plans before/after migration were compared and are
identical. Both report the existing libvirt interface-address drift on three
Windows domains (refreshed address lists are empty, while configuration declares
static management IPs). No replacement is planned. This drift was not applied or
silenced by the refactor.
