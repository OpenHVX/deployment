# OpenHVX platform in the nested lab

## Architecture and entry points

Each existing Windows/Hyper-V host runs two Ubuntu 24.04 infrastructure VMs:

| Hyper-V host | K3s server | Ceph node |
| --- | --- | --- |
| `lab-hv01` | `openhvx-cp-01` — `192.168.50.21` | `openhvx-ceph-01` — `192.168.50.31` |
| `lab-hv02` | `openhvx-cp-02` — `192.168.50.22` | `openhvx-ceph-02` — `192.168.50.32` |
| `lab-hv03` | `openhvx-cp-03` — `192.168.50.23` | `openhvx-ceph-03` — `192.168.50.33` |

Each VM has 4 vCPUs and 8 GiB fixed RAM. K3s system disks are 40 GiB; Ceph system
disks are 24 GiB with a separate, dedicated 60 GiB OSD disk. All are dynamically
allocated local VHDX files. Infrastructure bootstrap does not depend on Ceph or
OpenHVX. Windows hosts retain their 32 GiB allocation.

K3s `v1.34.13+k3s1` runs three schedulable servers with embedded etcd and encrypted
Kubernetes secrets. Ceph uses `quay.io/ceph/ceph:v19.2.3`, three monitors, three
OSDs, manager failover, and three iSCSI gateway daemons. The catalog contains a
verified Ubuntu image and its protected `base` snapshot.

The management VIP is `192.168.50.20`, provided by keepalived on the K3s VMs.
Traefik runs as a DaemonSet, one ingress instance per node. CoreDNS also has
three replicas spread across the nodes; a `.skip` file prevents bundled K3s
manifests from resetting the managed DNS configuration after restart. MongoDB has three
data-bearing replica-set members; RabbitMQ has three clustered members and v2
quorum queues. Auth, gateway, controller, and WS broker have three replicas each.
Broker identities and peer URLs use StatefulSet DNS. The Ceph connector has one
active pod and a persistent MongoDB journal. Agent journals remain on Windows.

## Deploy or resume

From the deployment repository, after the Windows lab hosts are available:

```bash
mise run lab:platform:up
```

For the complete host-plus-platform workflow:

```bash
mise run lab:up
```

The platform command prepares verified Ubuntu media, persistent secrets and
certificates, creates the VMs through Ansible/PowerShell, configures Linux, K3s,
Ceph and iSCSI, builds/imports images, initializes MongoDB, deploys the backend,
imports the catalog image, installs agents, and runs API/task acceptance.
It then disables first-admin registration. There is no unattended guest OS
reinstallation or automatic data-disk deletion on rerun.

A temporary HTTP server bound to `192.168.50.1:8765` serves only public OS media
and cloud-init seeds containing public SSH keys. It shuts down after VM creation.
Private SSH keys, credentials, and Kubernetes Secrets are never served there.
Windows downloads verify the prepared media checksums. The upstream Ubuntu image
is pinned to the `20261017` build and verified against Ubuntu's HTTPS SHA256 catalog.

The shared playbooks under `platform/ansible/playbooks/` accept an explicit
inventory. Lab-specific media, source packaging, certificates, and smoke adapters
live under `lab/scripts/`. `platform/kubernetes/render.py` requires explicit
`--work` and `--ca` paths; its current topology values target this lab.

The Linux management network uses an external Hyper-V vSwitch shared with the
Windows management interface. Existing hosts need an appropriate switch; automatic
creation currently recognizes the VirtIO adapter of this nested lab. The private
`fabric0` switch is a minimal isolated test network, not a tenant network design.

## Access and credentials

Endpoints resolve to the private VIP using sslip.io, avoiding workstation-wide DNS
changes. A local DNS server can instead map the certificate-covered `*.openhvx.lab`
names to the same VIP.

- Tenant API: `https://api.192-168-50-20.sslip.io`
- Admin API: `https://admin-api.192-168-50-20.sslip.io`
- Browser consoles: `wss://console.192-168-50-20.sslip.io/api/v1/console/...`
- Agent WS: `wss://ws.192-168-50-20.sslip.io/ws/...`
- Agent AMQP: TLS on `192.168.50.20:30671`.
- Ceph Dashboard/API: `https://192.168.50.30:8443`, a VIP following the active
  manager. Per-node standby redirects must not be used as connector login URLs.

Trust `.lab/ca.pem`; do not disable TLS verification. The gateway distinguishes
admin and tenant authentication by the HTTP hostname, so a bare IP is insufficient
for login. `curl --resolve` can be used when public wildcard DNS is unavailable.

Generated private files:

| File | Purpose |
| --- | --- |
| `.lab/infra/linux.yml` | Linux SSH inventory |
| `.lab/infra/id_ed25519` | Linux management SSH key |
| `.lab/infra/secrets.yml` | Persistent cluster and service secrets |
| `.lab/infra/admin.json` | Initial admin credentials |
| `.lab/infra/cli-config.json` | Dedicated lab CLI profile with a 30-day admin PAT |
| `.lab/infra/openhvx.yml` | Rendered Kubernetes resources, including secrets |
| `.lab/infra/image-tag` | Source-content deployment version |
| `.lab/infra/*-result.json` | Acceptance task records |

Use the lab CLI profile without overwriting your normal profile:

```bash
export HVX_CONFIG="$PWD/.lab/infra/cli-config.json"
export SSL_CERT_FILE="$PWD/.lab/ca.pem"
go -C ../openhvx-cli/src run ./cmd/hvx get images
```

Keep `.lab/` private and back it up securely. Never regenerate secrets to repair
an uncertain operation. The outbox encryption key, MongoDB data, Ceph data, storage
identity, and Windows journals must survive upgrades.

## Verification

```bash
mise run test
mise run lab:platform:verify
mise run lab:platform:storage-test
mise run lab:platform:failover-test
```

`lab:platform:verify` checks TLS, admin login, expected online v2 agents, image
listing, an echo command executed on Hyper-V, and idempotent HTTP replay.
`lab:platform:storage-test` uses the stable identity of one acceptance scenario:
clone an image, expose iSCSI, create/start a VM, then delete VM and disk through
the public API. Replaying a completed scenario checks its saved task outcomes;
it does not create a fresh VM. To intentionally run a new scenario, choose a new
explicit test identity:

```bash
mise exec -- python -u lab/scripts/smoke-storage.py --run acceptance-02
```

`lab:platform:failover-test` shuts down one K3s VM, measures VIP/API recovery,
executes a new echo task while that VM is down, and restores the VM in a `finally`
block. Run it only when no other deployment or effectful acceptance test is active.

If an operation becomes `reconciling`, preserve its key, journal, hold, and partial
resources. Do not switch test identities to retry that same operation.

## Verified storage-create reconciliation

`platform/kubernetes/operations/reconcile-storage-create.js` is an operator tool,
run inside the connector container. It is read-only by default. It compares the
accepted backend task and journal fingerprint, checks an already-finished unknown
execution, deterministic image identity, exact size, catalog/base ancestry, and
the expected iSCSI disk/portal mapping. With `--apply`, it persists an audited,
higher-sequence applied result before confirmed publication. It never reruns clone,
resize, or target creation. Repeating publication retains the same event identity.

```text
node /tmp/reconcile-storage-create.js TASK_ID hvwm
node /tmp/reconcile-storage-create.js TASK_ID hvwm --apply
```

Copy the versioned script into the connector pod before use. It requires privileged
access to both journal and backend data on the same MongoDB deployment. It only
handles conclusively verified `storage.create`; it is not a generic force-success
tool. `reconcile-storage-delete.js` separately handles a proven, unreferenced
accepted deletion: dry-run first; `--apply` may finish deleting its dedicated
target/image, but refuses active sessions and shared targets. It never disconnects
Windows initiators. Both tools preserve operation identity and audit evidence. Do not use it while an executor may still be working.

## Current limits

- This is a deployed lab, not a claim of production HA. Failure behavior must be
  measured separately for ingress, data services, consoles, storage, and host loss.
- The connector currently advertises one configured iSCSI portal (`192.168.50.31`)
  for new disks. Three gateway daemons do not by themselves provide initiator
  multipathing or transparent portal failover.
- Tenant routing, VyOS, Windows Failover Clustering, live migration, and tenant VM
  HA are not configured. Test VMs use `ha=false`.
- Databases use authenticated lab accounts; application-level per-database least
  privilege and full NetworkPolicy isolation remain hardening work. External
  management uses TLS; internal pod AMQP/MongoDB transport is currently plaintext.
- Local PVs are node-bound. Recovery of a lost disk requires reconstruction from
  surviving replicas. Replication is not an off-cluster backup strategy.
- Source snapshots are built on the first K3s VM with Docker and imported into
  all containerd instances. There is no production registry or release pipeline yet.
- Drain active operations before updating agents or the connector. Do not interrupt
  an effectful command merely because Kubernetes readiness reports healthy.
- The Express 5 query/path dictionary validation defect was fixed in the backend.
  Its regression tests cover resource listing and route parameters.

## Targeted image updates

`images.yml` accepts `image_names` to build/import only selected services.
The private `image-overrides.json` file in the artifact directory can map a service
name to a specific immutable image tag; rendering then updates only that service.
A full `lab:platform:up` clears overrides after importing the complete current
source image set, so later source deployments do not retain an obsolete hotfix.
