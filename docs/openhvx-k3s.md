# OpenHVX on K3s — implementation roadmap

This is the original planning checklist. For the deployed lab and actual validation
results, see [the runbook](lab-platform.md) and [status](status.md). Unchecked items
here are not a current inventory of missing implementation.

Status as of November 8, 2026: planned work, not an implemented deployment.
All checklist items remain to be implemented or validated. Application source:
`../openhvx-backend`. Deployment automation: this `deployment` repository.

## Target architecture

Each Hyper-V host will run one Ceph VM and one OpenHVX Linux VM.
The three OpenHVX VMs will form a K3s cluster with three servers running the
control plane, etcd, and workloads. No additional dedicated workers are needed.

| Host | Proposed VM | Role |
| --- | --- | --- |
| `lab-hv01` | `openhvx-cp-01` | K3s server, etcd, and workloads |
| `lab-hv02` | `openhvx-cp-02` | K3s server, etcd, and workloads |
| `lab-hv03` | `openhvx-cp-03` | K3s server, etcd, and workloads |

This is one logical backend: each OpenHVX controller can manage all agents,
regardless of its host. The application controller is separate from the Kubernetes
control plane. The target tolerates losing one host, not two out of three.
Preserve physical failure domains, including after VM migrations.
The single-workstation lab validates simulated failures only.

Tenant networking and VyOS remain undecided and out of scope. Management
connectivity required by the backend still needs to be defined. Ceph/Hyper-V
integration is a separate workstream.

## Current backend implementation

- Compose: Traefik, auth, gateway, controller, WS broker, standalone MongoDB, and
  a single RabbitMQ instance. Compose HTTPS labels do not provide HA K3s ingress.
- `src/service-ws-broker/src/app.ts`: `tunnels` and `activeByVm` are process-local;
  sockets and console exclusivity are not distributed.
- `src/service-api-gateway/src/ws/ws-proxy.ts`: a broker target without explicit
  routing to the tunnel owner.
- `src/service-controller/src/services/amqp.ts`: confirms and durable queues exist;
  replication and end-to-end recovery still need to be established.
- `src/service-controller/src/app.ts`: consumers and quota cleanup start in every
  instance; the reaper guard is process-local.
- See backend `docs/corrections-review-2026-11-07.md` for known limitations in
  quotas, gateway/controller trust, and tests.

## 1. K3s foundation — deployment

- [ ] Automate the three Linux VMs in Hyper-V, installation, and Ansible inventory.
  In the lab, they must run inside the Windows VMs, not directly under KVM.
- [ ] Size CPU/RAM/disks and update the lab resource budget, allowing enough
  capacity on the two remaining hosts after a failure.
- [ ] Define IPs, DNS, NTP, firewall rules, and inter-VM connectivity; choose
  pod/service CIDRs that do not overlap existing networks.
- [ ] Pin K3s, initialize etcd, and join the other two servers with consistent
  configuration and protected secrets.
- [ ] Provide a stable HA Kubernetes API endpoint, separate from application
  access and independent of any single server.
- [ ] Configure labels, affinities, and placement across failure domains.
- [ ] Back up etcd, the token, and configuration outside the cluster; test recovery.
- [ ] Ensure startup and emergency administration work without the OpenHVX API.

Proposal to validate: keep system disks and management data on local storage,
replicated by etcd/MongoDB/RabbitMQ, without a Ceph bootstrap dependency.
Define PVs, node affinity, and lost-member reconstruction: local volumes do not
follow pods automatically. Do not add another distributed storage layer by default.

## 2. Ingress and HA access — deployment

- [ ] Choose a failover VIP or an available external load balancer compatible with
  the lab; test loss of the node holding the address.
- [ ] Spread multiple Traefik instances across nodes. Choose either bundled K3s
  Traefik or a separate installation, without running both.
- [ ] Choose ServiceLB or a replacement. Multiple ingress replicas and a Service
  do not automatically make an external IP highly available.
- [ ] Translate Compose routes: tenant/admin APIs, auth, documentation, browser
  consoles, and agent WebSocket connections.
- [ ] Manage DNS, certificates, renewal, and TLS distribution across replicas.
- [ ] Configure WS upgrades, timeouts, limits, proxy headers, and client IP handling.
- [ ] Keep controller, MongoDB, and administration interfaces internal; provide
  private HA AMQP access for Windows agents outside Kubernetes.
- [ ] Remove tickets and tokens from all proxy logs.

## 3. Auth and HTTP state — backend

- [ ] Audit auth/gateway for local state incompatible with multiple instances;
  store shared persistent data in MongoDB.
- [ ] Distribute required JWT keys and define rotation and existing-token validity.
- [ ] Check expiration, revocation, logout, and single-use tickets; make single-use
  consumption atomic across instances.
- [ ] Decide whether rate limits are global or per replica and adapt counters.
- [ ] Choose gateway/controller authentication, add NetworkPolicies, and preserve
  identity-header sanitization.

Authentication sessions and console sessions are separate concerns.

## 4. Tunnel ownership and routing — backend and deployment

Proposal to validate: explicitly assign a broker to each tunnel. Sockets and
traffic stay on that broker; only coordination metadata is shared, for example
in MongoDB.

- [ ] Define a reachable identity per broker, availability, and lifecycle during
  restarts, address changes, and deployments.
- [ ] Select an available broker at creation and record owner, tunnel, tenant,
  VM, expiration, and lease generation.
- [ ] Include the owner reference in signed tickets; choose application proxying
  to the owner or dedicated routes. Describe the full ingress path for both
  agent and browser.
- [ ] Validate authorization and destination; reject arbitrary destinations and
  tickets from replaced generations.
- [ ] Replace `activeByVm` with shared atomic acquisition, expiration, renewal,
  and protection against stale owners returning after a partition.
- [ ] Handle duplicate opens, agent/browser connection order, closure, expiration,
  and owner unavailability.
- [ ] Implement draining and termination suitable for long-lived connections.
- [ ] Update agent and client: detect loss, request new tickets, and recreate a
  tunnel on an available broker.

Proposed contract: failure may interrupt a console, but reopening must work.
Transparent migration of active sockets is not a goal. Cookie/IP affinity is
insufficient: agent and browser are separate clients.

## 5. Controllers, tasks, and quotas — backend

- [ ] Audit concurrent writes, locks, and transitions before enabling three controllers.
- [ ] Carry an operation identifier through to the agent; define persistent
  deduplication for actions with side effects.
- [ ] Test crashes between publication, confirmation, execution, and result
  persistence; reconcile ambiguous states.
- [ ] Define HTTP/AMQP retries, timeouts, terminal errors, and invalid messages.
  A timeout does not mean the action did not happen.
- [ ] Make periodic work concurrency-safe or protect it with a shared lease;
  `reaperRunning` does not coordinate multiple processes.
- [ ] Use MongoDB transactions where quotas/holds require them and repair holds
  already stuck in intermediate states.
- [ ] Prevent old inventories/heartbeats from overwriting newer state during
  concurrent consumption.

Accept redeliveries and make effects idempotent. Confirms and acknowledgements
alone do not guarantee exactly-once business execution.

## 6. HA data — backend and deployment

### MongoDB

- [ ] Three data-bearing members, one per failure domain, with persistent
  identities/volumes, authentication, and private networking.
- [ ] Replica set URIs, member discovery, write concern, timeouts, and client
  recovery during elections.
- [ ] Migrate standalone data and indexes; select supported versions rather than
  copying Compose tags.
- [ ] Test off-cluster backup/restore and member reconstruction.

### RabbitMQ

- [ ] Three members with persistent storage and separate placement.
- [ ] Inventory backend/agent queues; choose quorum queues for messages that must
  survive member loss. Durable does not mean replicated.
- [ ] Migrate existing queues: their type cannot change through redeclaration.
  Align agent and backend declarations.
- [ ] Check TTL, expiration, routing, unroutable messages, dead letters, prefetch,
  acknowledgements, and confirms against the selected topology.
- [ ] Provide private HA AMQP access, reconnection, authentication, and transport
  protection for agents; test queue-leader loss and redelivery.

Data replication does not replace backups.

## 7. Packaging and operations — deployment

- [ ] Publish images with pinned versions/digests; replace Compose `build`, labels,
  networks, and `container_name` with Kubernetes resources. Choose Helm or Kustomize.
- [ ] Define replicas, placement, resources, probes, and graceful shutdown; extend
  health endpoints. `depends_on` is not Kubernetes orchestration.
- [ ] Define disruption budgets for maintenance: they do not protect against
  physical failures or create spare capacity.
- [ ] Manage ConfigMaps, Secrets, SOPS/age, at-rest protection, and minimal RBAC.
- [ ] Replace controller `/mnt/openhvx:/share:ro` with file access defined for all
  replicas, or adapt the backend.
- [ ] Add mise tasks and Ansible roles without depending on OpenHVX to repair itself.
- [ ] Add logs, metrics, and correlation for quorums, queues, stuck tasks,
  dependencies, tunnel owners, and reconnections.
- [ ] Document installation, migration, rollback, secrets, maintenance, and recovery.

## Delivery sequence and acceptance

1. Define tunnel, exclusivity, idempotency, and retry contracts; write backend tests.
2. Provision K3s, volumes, stable endpoints, and agent connectivity.
3. Deploy HA data services and validate migration/recovery before multiple controllers.
4. Deploy the adapted backend and tunnel routing.
5. Measure failure behavior and set recovery objectives from the results.

| Required scenario | Expected outcome |
| --- | --- |
| Lose an OpenHVX VM, then a Hyper-V host | Quorums preserved, API access automatically restored |
| Lose ingress/K3s API address holder | Stable endpoint reachable without manual intervention |
| Lose MongoDB primary or RabbitMQ leader | Reconnect after election; data guarantees respected |
| Controller crash during VM creation | No second creation; final state reconciled |
| Concurrent consoles through two brokers | Cluster-wide exclusivity preserved |
| Broker loss during a console | Loss detected; a new tunnel can open elsewhere |
| Broker returns after lease expiration | Stale ownership and tickets rejected |
| Rolling update and drain | Availability follows the contract; reconnect if needed |
| Restore from off-cluster backups | Reproducible recovery for K3s and application data |

Record durations, errors, retries, and observed duplicates.

## References

- [K3s: embedded etcd HA](https://docs.k3s.io/installation/ha-embedded/)
- [K3s: schedulable servers without dedicated agents](https://docs.k3s.io/datastore/ha)
- [K3s: Traefik and ServiceLB](https://docs.k3s.io/networking/networking-services)
- [MongoDB: replica set members](https://www.mongodb.com/docs/manual/core/replica-set-members/)
- [RabbitMQ: quorum queues](https://www.rabbitmq.com/docs/quorum-queues)
