# Maintaining deployment automation

**Type:** Reference

**Status:** Current implementation; maintenance routing and Ceph reconciliation still require lab acceptance

**Scope:** Execution order, ownership, failure handling and safe changes to the automation

[Documentation index](index.md)

## Start with the execution order

Read `lab/scripts/platform-up.py::main()` first. It is the lab's sequence of named
stages, not an infrastructure model. Follow the calls into these files:

| Concern | Start here | What belongs there |
| --- | --- | --- |
| Operator commands | `.mise.toml` | Short, visible entry points |
| Exclusive workstation operation | `scripts/with-lab-lock.sh` | One lock for nested lab commands |
| Lab arguments and Ansible invocation | `lab/scripts/lab_runtime.py` | Paths, process lock and runner arguments only |
| Infrastructure media | `lab/scripts/prepare-infra.py` | Source declarations, seed verification and generated connection inventory |
| Persistent credentials | `lab/scripts/prepare-platform-secrets.py` | Reuse identities; refuse accidental replacement |
| Windows agent packaging | `lab/scripts/prepare-agent.py` | Compile/package only; no installation |
| Application sources | `lab/scripts/image_sources.py` | New release directory and source snapshots |
| Application image build | `ansible/playbooks/images.yml` and `ansible/roles/container_images/tasks/` | Preflight, clean build contexts, provenance and imports |
| Deployment maintenance | `ansible/playbooks/maintenance.yml` and `ansible/roles/deployment_maintenance/tasks/` | Close admission, verify the gate, drain tasks, reopen after readiness |
| Component configuration | `ansible/playbooks/` and `ansible/roles/` | Target hosts/order in playbooks, behavior in roles |
| Windows/Hyper-V operations | `ansible/powershell/` | Native APIs and VM ownership checks |
| Application resources | `kubernetes/base/` and `kubernetes/overlays/lab/` | Workloads and the selected release |

Do not put new host configuration into the Python orchestrator. Do not make an
Ansible task call another lab deployment script. Keep the call chain one way:
operator command → lab adapter → playbook → component task/native operation.

## Application release lifecycle

1. `lab:images:build` creates `.lab/infra/releases/lab-UUID/`.
2. Source archives and a provenance hash are written inside that directory.
3. Every K3s node is checked for an existing reference with this release tag.
4. Docker builds from a clean directory specific to this release.
5. The builder records image IDs and the SHA256 of the exported bundle in
   `image-receipt.json`. Each node verifies that bundle checksum before importing.
6. Only after all imports succeed does `.lab/infra/image-tag` identify this
   candidate. The tracked Kubernetes overlay is never changed automatically.

A source hash is not proof that a rebuild produces identical bytes. Upstream base
images/packages can change. Tags are therefore unique per attempt, and an imported
tag cannot be reused by the build workflow. Image IDs in the receipt identify the
built Docker configurations/rootfs; they are not registry manifest digests.
There is no registry-based digest deployment in this lab yet.

If a build/import fails, retain the failed release directory for diagnosis and
start another build. The prior successful candidate file remains unchanged. A
partial import must not be repaired by overwriting the same tag. Promote only the
new successful candidate, following the [setup runbook](10-lab-setup-and-access.md).

## Bootstrap media are immutable inputs

Cloud-init configures first boot. Changing its source files does not reconfigure a
running guest. Before publishing inventories, `prepare-infra.py` extracts every
existing ISO into temporary storage and compares its actual content with the
requested declaration. A mismatch stops preparation without rewriting seeds or
inventories. Windows also verifies the seed attached to an existing VM.

If an address or SSH key must change, first establish what the guest is using.
Use a planned guest maintenance or rebuild procedure; do not delete an ISO merely
to make the validation pass. Keep the existing SSH identity, service credentials,
VM ownership receipts and data disks. A missing credential for an existing
installation requires recovery from backup.

## Maintenance and recovery

Full and network-only platform deployment use the same admission procedure.
`lab:hosts:up` also enters it when a Linux inventory already exists, before changing
simulated hosts. A standalone host run leaves the gate closed until the platform
is resumed. Low-level Terraform/Ansible commands do not establish this window
for you; enter it explicitly before manual maintenance:

```bash
mise run lab:maintenance:enter
```

The shared procedure is:

1. Install the temporary resources from `kubernetes/maintenance/api-gate.yaml`.
   A high-priority Traefik route denies public `/api` requests with HTTP 403.
   Its backend is Traefik's built-in dummy service, independent of rolling pods.
2. Verify that route through every K3s ingress node using the trusted lab CA.
3. Wait 30 seconds for requests already inside the gateway's upstream timeout.
4. Check durable tasks up to 30 times, with 5 seconds between observations, until
   they leave `queued`, `sent` and `reconciling`. MongoDB connection attempts are
   bounded to 5 seconds. An unresolved operation or failed observation stops deployment.
5. Apply infrastructure/application changes and wait for workload readiness.
6. Remove the maintenance route explicitly, then run public API acceptance.

The gate is deliberately outside the normal Kustomize base: applying application
manifests must not remove it. Agent/AMQP traffic stays available for accepted work
to finish. Operators must stop any client that bypasses public ingress; this is
not a distributed maintenance API for direct internal clients or established
long-lived connections. First installation skips the gate only when neither the
controller nor MongoDB workload exists.

On failure, the gate remains installed if it was created. Inspect the failed
Ansible task and Kubernetes events, repair the cause, then rerun deployment.
If you explicitly choose to resume the current workloads instead:

```bash
mise run lab:maintenance:resume
```

The resume procedure waits for all application workloads before removing the gate;
it does not roll back images or repair uncertain operations. Restore the selected
previous release explicitly when rollback is needed. Never remove journal entries
or task holds to force a rollout through.

SSH/kubeconfig access remains available during admission maintenance. See
[setup and access](10-lab-setup-and-access.md#k3s-access). A failed post-deployment
acceptance check occurs after admission was reopened; inspect logs and saved
results rather than assuming the gate is still installed.

## Concurrency and entry points

Use the `mise` commands for lab mutations. They share `.lab/deployment.lock` using
`flock`; nested commands inherit ownership. The build, platform, network and media
Python entry points also acquire this lock when invoked directly. Do not run
low-level playbooks or native scripts concurrently with the lab commands.

The lock belongs to the workstation process, not a cluster service. It does not
coordinate multiple deployment workstations or administrators using kubectl.
Do not delete its file while an operation runs: a new inode could permit another
operation to enter. A normal process exit releases the lock automatically.

## Writing understandable tasks and scripts

- Name functions/stages for their operational purpose. Keep `main()` readable as
  a sequence; place media serving or packaging details in named functions.
- Comment why a step exists, what it owns, and what must happen after failure.
  Avoid comments that merely restate a module name or assignment.
- Keep variable names explicit and use conventional Ansible modules first.
- For command tasks, inspect state before mutation. `changed_when: false` belongs
  on observation commands, not configuration writes. Document comparison rules.
- Preserve identity before attempting repair. Fail clearly when adoption,
  resizing or bootstrap changes need operator decisions.
- Keep credentials out of output, use `no_log` on private tasks, and set file
  permissions before writing secrets.

The Ceph role now reads host addresses, memory targets, monitor placement, pool
application metadata and the live iSCSI spec before deciding to mutate them. Its
comparisons cover fields owned by deployment, allowing Ceph-added defaults.
Live reconciliation still needs a controlled first/second-run acceptance.

## Validation before deployment

```bash
mise run test
```

In addition to renderer/ownership contracts, the offline suite checks actual ISO
content, stale build file removal through Ansible, release publication on failure,
maintenance control flow and lock contention. It does not prove Traefik routing,
Ceph API behavior or full installation convergence on a live lab.

Before relying on these changes, perform a controlled lab acceptance: verify API
403 during maintenance, active-task refusal, successful reopening, a failed-rollout
recovery, and a second configuration run. Compare VM identities and retain evidence.
Do not claim `changed=0` based only on syntax validation.

## Implementation references

- [Traefik chart examples: internal dummy service in an IngressRoute](https://github.com/traefik/traefik-helm-chart/blob/master/EXAMPLES.md)
- [Ceph service management and exported specifications](https://docs.ceph.com/en/latest/cephadm/services/)
- [Documentation standard](09-documentation-standard.md)
