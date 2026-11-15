# Deployment context

The [documentation index](docs/index.md) is the entry point for this repository.
Use [repository structure](docs/02-deployment-structure.md) for source ownership and
[lab deployment](docs/05-lab-platform.md) for operational procedures.

OpenHVX remains the source of truth for tenant resources. This repository owns
management infrastructure. Preserve `.lab/` credentials, journals and ownership
receipts, along with OpenTofu state. Never adopt or replace uncertain resources
implicitly.

The network executor currently plans logical VPC operations. VyOS lifecycle is
implemented separately; tenant forwarding, provider API configuration and network
failover remain unimplemented. See [current status](docs/01-status.md).

Earlier decisions are preserved in [historical context](docs/history/01-lab-context.md).
They do not override the current guides.
