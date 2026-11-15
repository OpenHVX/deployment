# Network PoC

The PoC provisions logical VPC intent in OpenHVX and sends durable planning jobs
to a separate, three-replica TypeScript Network Orchestrator. It does not yet
implement provider execution, subnets, NIC attachment, VyOS provider
configuration, VRRP, NAT or packet forwarding. `planned` never means `ready`.

Backend design: `../openhvx-backend/docs/network-design.md`.
The backend branch is `feature/op/network`. This deployment directory has no Git
repository at the time this increment was prepared.

## Logical control-plane PoC

```bash
mise run lab:network:deploy
mise run lab:network:verify
```

The deployment task requires no unresolved backend tasks. It builds controller,
gateway and Network Orchestrator images, imports them on all K3s nodes and rolls
out those services.
It preserves the default image tag for other services and saves their image
overrides. It opts into the controller's `NETWORK_POC_ENABLED=true` feature through
the deployment and `.lab/infra/network-settings.json`. The manifest renderer reads
that file so a later normal deployment preserves the opt-in. No automatic rollback
is attempted after a partial rollout; inspect Kubernetes state and rerun the task.

The verification task uses trusted public TLS and a disposable tenant. It checks
creation, asynchronous planning through RabbitMQ, replay, changed-content conflict,
two overlapping VPC CIDRs, the third
VPC exceeding quota, quota reduction, deletion protection and cleanup. It writes
`.lab/infra/network-result.json`. It does not test router availability or traffic.

## VyOS VM lifecycle

The [VyOS lifecycle runbook](vyos-lifecycle.md) owns image construction, deployment,
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
The dedicated `network-orchestrator.yml` playbook applies only its Deployment and
private environment. The worker remains `plan-only`, and `/vpcs/{id}/plan` reports
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
