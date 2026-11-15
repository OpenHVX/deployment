# OpenHVX deployment

Infrastructure automation for OpenHVX. OpenTofu provisions the simulated Windows
hosts in the local KVM lab; Ansible and PowerShell configure existing Hyper-V
hosts and management VMs; Kubernetes manifests declare the application release.
OpenHVX remains the source of truth for tenant resources.

Start with the [documentation index](docs/index.md).

## Local setup

Run from this repository's root with `mise` installed:

```bash
mise install
mise run bootstrap
mise run test
```

`bootstrap` installs Python dependencies in `.venv/` and Ansible collections in
`.ansible/`. System prerequisites are described in the relevant runbook.
`test` performs offline validation; it does not deploy the platform.

## Common tasks

| Task | Guide |
| --- | --- |
| Install the lab and connect to K3s/OpenHVX | [Lab setup and access](docs/10-lab-setup-and-access.md) |
| Understand the layout and edit configuration | [Repository structure](docs/02-deployment-structure.md) |
| Provision Windows hosts on blank lab disks | [Windows installation](docs/04-unattended-windows.md) |
| Deploy or resume OpenHVX | [Lab deployment](docs/05-lab-platform.md) |
| Manage the VyOS VMs | [VyOS lifecycle](docs/06-vyos-lifecycle.md) |
| Inspect the network planning contract and results | [Network PoC](docs/07-network-poc.md) |
| Check implemented capabilities and limits | [Current status](docs/01-status.md) |

For an existing non-lab host inventory, the shared runner requires an explicit
inventory and credentials; it does not load lab secrets:

```bash
PLATFORM_INVENTORY=/absolute/path/to/inventory.yml mise run platform:deploy
```

This entry point configures the Windows/Hyper-V baseline. Follow the detailed lab
runbook for infrastructure VMs and application deployment.

## State and credentials

Keep `.lab/`, local OpenTofu state/plans and installation media private. Preserve
existing credentials, SSH trust and VM ownership receipts during recovery. See
[configuration and state ownership](docs/02-deployment-structure.md#configuration-secrets-and-state)
before modifying these files. No lab acceptance result establishes production HA.
