# Lab setup and access

**Type:** Runbook

**Status:** Current procedure; documentation examples have not been executed as a new installation

**Scope:** Install the nested lab, access K3s and connect to OpenHVX

[Documentation index](index.md)

## Purpose

Use this guide for the first installation and day-to-day access. All workstation
commands run from the `deployment` repository root unless stated otherwise.
If the lab is already deployed, start at [K3s access](#k3s-access) or
[OpenHVX access](#openhvx-access); do not reprovision it to obtain access.

Deployment changes infrastructure. Inspection commands are identified separately;
acceptance tests may create tenants or execute tasks. Keep existing credentials,
state and ownership receipts when resuming an installation.

## Prerequisites

- A Linux x86-64 workstation with nested KVM enabled, accessible `/dev/kvm`,
  libvirt and permission to use `qemu:///system`.
- `mise`, Git, Go for the Windows agent/CLI, OpenSSH, QEMU image tools, OVMF,
  `7z`, `xorriso`, `openssl`, `curl`, `setfacl` and `iproute2`.
- A Windows Server ISO and sufficient space for installation media.
- Sibling source repositories: `../openhvx-backend`, `../openhvx-agent` and
  `../openhvx-ceph-connector`. CLI examples also require `../openhvx-cli`.
- Internet access for tools, OS images, packages and container dependencies.
- For optional workstation Kubernetes access, a `kubectl` client compatible with
  the configured K3s version. The SSH access method uses the client on the node.

The default simulated hosts each have 8 vCPUs, 32 GiB RAM and a 200 GiB system
disk. Workstation checks require 24 vCPUs plus 2 CPUs of headroom, 96 GiB available
RAM plus 4 GiB of headroom, and 600 GiB free disk space plus 10 GiB of headroom.
Media preparation additionally needs approximately 25 GiB of temporary space.
See [nested virtualization](03-nested-virtualization.md) for diagnostics.

## Configuration

The current lab uses these addresses:

| Resource | Address or path |
| --- | --- |
| Management network / workstation gateway | `192.168.50.0/24` / `192.168.50.1` |
| Windows/Hyper-V hosts | `192.168.50.10`–`192.168.50.12` |
| K3s servers | `192.168.50.21`–`192.168.50.23` |
| K3s API | `https://192.168.50.20:6443` |
| OpenHVX ingress | `192.168.50.20:443` |
| Ceph Dashboard/API | `https://192.168.50.30:8443` |
| Optional management-only VyOS VMs | `192.168.50.41`–`192.168.50.43` |

The workstation must reach the management network. Avoid conflicting LAN or VPN
routes. The commands below assume the versioned lab addressing; changing only the
OpenTofu CIDR does not update every platform address or certificate.

Review [the inventory](../environments/lab/inventory.yml), host variables under
`environments/lab/host_vars/` and the local OpenTofu configuration. For a new lab,
copy the example only if no local configuration exists:

```bash
cp -n tofu/environments/lab/lab.tfvars.example \
  tofu/environments/lab/lab.auto.tfvars
```

Edit `tofu/environments/lab/lab.auto.tfvars`: set `os_iso_path` to the absolute
Windows ISO path and verify `firmware_path`. Keep `host_count = 3` for this declared
inventory. Local `.tfvars` files are ignored by Git.

## Procedure

### 1. Install tools and validate the workstation

```bash
mise install
mise run bootstrap
mise run check:host
mise run test
```

Stop if prerequisite or static checks fail. They do not configure the lab. System
packages and libvirt permissions must be prepared separately.

### 2. Provision and configure the Windows hosts

This installs Windows on blank disks. Installation media erase disk 0; use only
the simulated hosts intended for this installation.

```bash
mise run lab:hosts:up
mise run ansible:configure
mise run test:lab
```

The first command prepares media, creates/applies an OpenTofu plan and waits for
WinRM HTTPS. Configuration enables the Windows/Hyper-V baseline. `test:lab`
starts and deletes a temporary diskless nested VM per host. Expected result: all
three hosts are reachable and the nested startup check succeeds.

The Administrator password is stored in `.lab/windows-password`. For RDP, use
`Administrator` and one of the Windows host addresses, then retrieve the password
locally from that protected file. Do not paste it into logs or tickets. See
[Windows installation](04-unattended-windows.md) for bootstrap logs and recovery.

### 3. Deploy K3s and Ceph infrastructure

```bash
mise run lab:infrastructure:up
```

This prepares the persistent credentials and SSH identity, creates three K3s VMs
and three Ceph VMs, and configures their services. It also compiles the Windows
agent package. It stops before application deployment. Expected result: the
infrastructure command completes and the three K3s nodes are Ready; use the
[K3s SSH check](#access-through-ssh) below to confirm.

### 4. Build and select the application release

```bash
mise run lab:images:build
```

This snapshots the sibling sources, builds their images on the first K3s node and
imports the image bundle on all K3s nodes. The unique release tag is saved in
`.lab/infra/image-tag` only after successful imports; its artifacts and checksum
receipt remain in `.lab/infra/releases/TAG/`. It does not select the deployed release automatically.

For a fresh installation, select that same tag for all six application images:

```bash
export OPENHVX_IMAGE_TAG="$(cat .lab/infra/image-tag)"
mise exec -- yq -i '.images[].newTag = strenv(OPENHVX_IMAGE_TAG)' \
  kubernetes/overlays/lab/kustomization.yaml
git diff -- kubernetes/overlays/lab/kustomization.yaml
mise run kubernetes:inspect
```

Review the configuration diff before continuing. All selected images must already
be imported. Existing installations can retain their declared image versions.

### 5. Deploy OpenHVX and create the first administrator

For an existing platform, deployment temporarily closes public API admission and
waits for accepted operations to finish. HTTP 403 during this window is expected.
After a failed rollout, use the [maintenance recovery procedure](11-maintaining-deployment.md#maintenance-and-recovery).


For a new lab only, enable first-administrator registration explicitly:

```bash
mise exec -- yq -i '.register_enabled = "true"' \
  kubernetes/overlays/lab/settings.yml
mise run lab:platform:up
```

The platform command deploys the declared applications, initializes data services,
imports the image catalog, installs agents and runs the API/task acceptance check.
That check creates the initial administrator using `.lab/infra/admin.json`, then
creates the lab CLI profile in `.lab/infra/cli-config.json`. It also creates the
`lab-smoke` tenant and executes an echo task.

After successful administrator creation, close registration and deploy again:

```bash
mise exec -- yq -i '.register_enabled = "false"' \
  kubernetes/overlays/lab/settings.yml
mise run lab:platform:up
```

Keep registration closed when resuming an existing lab. A failed acceptance check
does not justify deleting credentials or changing the administrator identity.

### 6. Optionally deploy the VyOS management VMs

```bash
mise run lab:network:vyos-image
mise run lab:network:vyos-up
mise run lab:network:vyos-status
mise run lab:network:vyos-verify
```

Expected result: one owned, SSH-verified VyOS VM per Hyper-V host. This is separate
from VPC planning; it does not enable tenant forwarding or router failover. See
[VyOS lifecycle](06-vyos-lifecycle.md) before rebuild or destruction.

## K3s access

### Access through SSH

After infrastructure provisioning, use the generated Linux key and known-hosts
file. This read-only command runs the node's Kubernetes client without installing
`kubectl` on the workstation:

```bash
ssh -i .lab/infra/id_ed25519 \
  -o BatchMode=yes \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=.lab/infra/known_hosts \
  ubuntu@192.168.50.21 'sudo k3s kubectl get nodes -o wide'
```

Expect `openhvx-cp-01`, `openhvx-cp-02` and `openhvx-cp-03` to be Ready. To open an
interactive shell, omit the remote command and use `sudo k3s kubectl` on the node.
The other K3s nodes are reachable at `.22` and `.23` with the same management key.
If SSH reports an unknown or changed host key, verify the node identity before
updating trust; do not disable host-key checking.

### Access from the workstation with kubectl

The exported kubeconfig grants cluster administrator access. Store it privately,
keep it out of Git and do not print its embedded credentials. This copies the
node's kubeconfig and replaces its loopback endpoint with the management VIP:

```bash
umask 077
K3S_KUBECONFIG_COPY="$(mktemp .lab/infra/kubeconfig.XXXXXX)"
ssh -i .lab/infra/id_ed25519 \
  -o BatchMode=yes \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=.lab/infra/known_hosts \
  ubuntu@192.168.50.21 'sudo cat /etc/rancher/k3s/k3s.yaml' \
  > "$K3S_KUBECONFIG_COPY"
```

Proceed only if SSH exits successfully and the copied file is nonempty. If it
fails, remove the temporary file and diagnose SSH before exporting credentials.
After a successful copy:

```bash
mv "$K3S_KUBECONFIG_COPY" .lab/infra/kubeconfig.yml
chmod 600 .lab/infra/kubeconfig.yml
mise exec -- python - <<'PY'
from pathlib import Path
import yaml
path = Path('.lab/infra/kubeconfig.yml')
config = yaml.safe_load(path.read_text())
for cluster in config['clusters']:
    cluster['cluster']['server'] = 'https://192.168.50.20:6443'
path.write_text(yaml.safe_dump(config, sort_keys=False))
PY
export KUBECONFIG="$PWD/.lab/infra/kubeconfig.yml"
kubectl get nodes -o wide
kubectl -n openhvx get pods -o wide
```

This dedicated `KUBECONFIG` leaves `~/.kube/config` untouched.
The kubeconfig embeds the K3s API's own CA; `.lab/ca.pem` is the separate trust
anchor for OpenHVX ingress and lab management services. No insecure TLS option is
needed. Refresh the exported kubeconfig from a healthy node after credential
rotation or certificate expiry.

### Inspect workloads and follow logs

These workstation commands require the exported `KUBECONFIG` above. Alternatively,
run the equivalent `sudo k3s kubectl` commands in the SSH shell.

```bash
kubectl -n openhvx get deployments,statefulsets,services,ingresses
kubectl -n openhvx get events --sort-by=.metadata.creationTimestamp
kubectl -n openhvx logs -l app=controller --prefix --tail=100 --follow
```

Stop the log stream with Ctrl+C. For the executor or gateway, select their labels:

```bash
kubectl -n openhvx logs -l app=network-orchestrator --prefix --tail=100 --follow
kubectl -n openhvx logs -l app=api-gateway --prefix --tail=100 --follow
```

For an individual failed pod, replace `POD_NAME` with a name from `get pods`:

```bash
kubectl -n openhvx describe pod POD_NAME
kubectl -n openhvx logs POD_NAME --previous --tail=100
```

`--previous` is useful only when the container has restarted. Treat application
logs as private operational data. To inspect the actual persisted network command
and result JSON rather than logs, run `mise run lab:network:inspect` as described
in the [network PoC runbook](07-network-poc.md).

## OpenHVX access

### Endpoints and trust

| Access | Endpoint |
| --- | --- |
| Admin API | `https://admin-api.192-168-50-20.sslip.io` |
| Tenant API | `https://api.192-168-50-20.sslip.io` |
| Browser console transport | `wss://console.192-168-50-20.sslip.io/api/v1/console/...` |

These hostnames resolve to the private ingress VIP. Trust `.lab/ca.pem` in your
client. The manifests in this repository deploy the backend APIs and console
transport; they do not deploy a web administration frontend. Opening the API URL
in a browser is not an administration UI login procedure.

To check public HTTPS and controller health without relying on wildcard DNS:

```bash
curl --fail --show-error --silent \
  --cacert .lab/ca.pem \
  --resolve admin-api.openhvx.lab:443:192.168.50.20 \
  https://admin-api.openhvx.lab/api/v1/healthz
```

Expected result: an HTTP success response from the health endpoint. This is not
a complete authentication or task-execution check. Use a certificate-covered
hostname; a bare IP does not select the correct admin/tenant authentication route.

### Administrator credentials and API login

The acceptance check stores the initial administrator email and password in
`.lab/infra/admin.json`. Retrieve them locally when needed. The following command
uses that file without putting the password in command-line arguments, and saves
the login response privately instead of printing the access token:

```bash
umask 077
curl --fail-with-body --show-error --silent \
  --cacert .lab/ca.pem \
  --resolve admin-api.openhvx.lab:443:192.168.50.20 \
  --header 'Content-Type: application/json' \
  --data-binary @.lab/infra/admin.json \
  --output .lab/infra/admin-login.json \
  https://admin-api.openhvx.lab/api/v1/admin/auth/login
chmod 600 .lab/infra/admin-login.json
```

Expected result: HTTP success and an access token in the private response file.
Do not commit or share that response. The CLI below provides a simpler route for
normal operator requests.

### Use the OpenHVX CLI

The acceptance check creates a dedicated profile with a 30-day administrator PAT.
Use it without overwriting your regular CLI configuration:

```bash
export HVX_CONFIG="$PWD/.lab/infra/cli-config.json"
export SSL_CERT_FILE="$PWD/.lab/ca.pem"
go -C ../openhvx-cli/src run ./cmd/hvx get images
```

Expected result: the image catalog, using the lab administrator profile and trusted
TLS. Go may download build dependencies on the first invocation. Run
`go -C ../openhvx-cli/src run ./cmd/hvx --help` for supported operations.
If the PAT expires, renew it through the authentication workflow and update this
private profile; rerunning acceptance does not rotate an existing profile.

## Verification

For an existing installation, first inspect nodes, workloads and public HTTPS
using the read-only commands above. Then, when task execution is acceptable:

```bash
mise run lab:platform:verify
```

This exercises admin authentication, agent registration state, the image catalog,
an echo command and idempotent replay. It can create the lab tenant/profile and
executes a backend task; it is not a read-only health probe. Evidence is written to
`.lab/infra/smoke-result.json`.

For network planning acceptance, `mise run lab:network:verify` creates and cleans
up a disposable tenant/VPC scenario, with evidence in `.lab/infra/network-result.json`.
Storage and failover acceptance have additional side effects; follow the
[platform runbook](05-lab-platform.md#verification) before running them.

## Recovery and limitations

| Symptom | First checks |
| --- | --- |
| SSH fails | Host/VM state, management routes, key file and trusted host identity |
| K3s API is unreachable | SSH to a node; inspect `sudo systemctl status k3s` and `sudo journalctl -u k3s -n 100`; check VIP ownership |
| Pods remain Pending | Node readiness, resources and local PV placement; inspect the pod/events |
| Pods report ImagePullBackOff | Confirm the declared tag was built/imported on every K3s node |
| HTTPS certificate failure | CA path, certificate expiry and hostname; do not bypass TLS verification |
| DNS fails for sslip.io | Use the documented `curl --resolve` method or configure trusted local DNS |
| API returns 403 during/after deployment | Inspect the maintenance route and failed deployment; follow the maintenance recovery procedure |
| Login fails | Admin hostname, saved account, initial registration policy and auth logs |
| CLI returns unauthorized | Profile selection and PAT expiry |

Preserve OpenTofu state, `.lab/` identities and data journals. The known libvirt
interface-address drift is documented in [current status](01-status.md); review a
plan before applying rather than treating a rerun as an inspection command.

## Related documents

- [Repository structure](02-deployment-structure.md)
- [Windows installation](04-unattended-windows.md)
- [Platform operations](05-lab-platform.md)
- [VyOS lifecycle](06-vyos-lifecycle.md)
- [Network PoC](07-network-poc.md)
