# Network PoC

**Type:** Runbook

**Status:** Experimental; planning only

**Scope:** Deploy, verify and inspect logical VPC planning

[Documentation index](index.md)

The PoC provisions logical VPC intent in OpenHVX and sends durable planning jobs
to a separate, three-replica TypeScript Network Orchestrator. It does not yet
implement provider execution, subnets, NIC attachment, VyOS provider
configuration, VRRP, NAT or packet forwarding. `planned` never means `ready`.

Backend design: [network architecture](../../openhvx-backend/docs/network-design.md).
The backend branch is `feature/op/network`. Deployment changes are tracked in their own local Git repository.

## Prerequisites

The existing platform must be healthy, with the desired images imported on K3s
nodes. Drain unresolved backend tasks before updating these workloads. The lab
adapter uses existing credentials and the trusted CA under `.lab/`.

## Procedure

```bash
mise run lab:network:deploy
```

The deployment task closes public API admission and waits for unresolved backend tasks. Build/import images
separately with `mise run lab:images:build`, review their tags in
`kubernetes/overlays/lab/kustomization.yaml`, then apply the declared release.
`settings.yml` explicitly enables `NETWORK_POC_ENABLED`; no private runtime flag
controls the desired release. Ansible applies the controller, gateway and executor
manifests through one path. Inspect Kubernetes state after a partial rollout before
rerunning. The gate remains closed after a failed rollout; follow
[maintenance recovery](11-maintaining-deployment.md#maintenance-and-recovery).
See [deployment structure](02-deployment-structure.md).

## VyOS VM lifecycle

The [VyOS lifecycle runbook](06-vyos-lifecycle.md) owns image construction, deployment,
status, guest verification and targeted destruction independently of VPC planning.

```bash
mise run lab:network:vyos-image
mise run lab:network:vyos-up
mise run lab:network:vyos-status
mise run lab:network:vyos-verify
mise run lab:network:vyos-down
```

The final command previews deletion. Applying it requires the deployment UUID
shown by the preview. The image factory replaces the earlier requirement to
supply a manually prepared cloud-init VHDX; an explicit image manifest remains
supported. These are management-only router VMs, with no tenant routing or HA.

The executor uses `openhvx-network` as a separate MongoDB journal database.
The dedicated `network-orchestrator.yml` playbook applies the declared controller, gateway, executor and
their private environments. The worker remains `plan-only`, and `/vpcs/{id}/plan` reports
its observation without marking the VPC ready. Existing planned VPCs can request
a first plan by POSTing an empty body to that endpoint.

## Inspect actual command and result JSON

`mise run lab:network:inspect` prints the latest persisted controller envelope,
its decoded command body, and the matching executor result. It only reads MongoDB
through the running pods; it does not consume or acknowledge RabbitMQ messages.
Execution records survive the acceptance test's resource cleanup.

To select an operation explicitly:

```bash
mise exec -- python lab/scripts/inspect-network.py --operation-id OPERATION_UUID
```

## Verification

```bash
mise run lab:network:verify
```

The verification task uses trusted public TLS and a disposable tenant. It checks
creation, asynchronous planning through RabbitMQ, replay, changed-content conflict,
two overlapping VPC CIDRs, the third
VPC exceeding quota, quota reduction, deletion protection and cleanup. It writes
`.lab/infra/network-result.json`. It does not test router availability or traffic.

## Limitations

A successful planning result does not configure VyOS or host networking. This PoC
does not validate packet forwarding, NAT or router failover. Inspect executor
results before interpreting the VPC's state; `planned` is not `ready`.

## Related documents

- [VyOS lifecycle](06-vyos-lifecycle.md)
- [Repository structure](02-deployment-structure.md)
- [Current status](01-status.md)
