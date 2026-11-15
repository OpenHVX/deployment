# OpenHVX Kubernetes resources

**Type:** Component reference

**Status:** Current

**Scope:** Kubernetes resources and private rendering

`base/` contains plain Kubernetes YAML. `overlays/lab/kustomization.yaml` declares
application image tags; `settings.yml` declares registration and network policy.

```bash
mise run kubernetes:inspect  # public resources; no credentials or apply
mise run kubernetes:render   # .lab/infra/openhvx.yml, private mode 0600
```

The private renderer fills `overlays/lab/private/*.yaml.j2` from existing credentials
and TLS material, preserves configuration rollout checksums, and runs Kustomize.
It never applies resources. Hidden image overrides or bootstrap markers have no
effect. Build/import images separately, review the declared versions, then apply.

The resources retain MongoDB/RabbitMQ replication, three backend and WS broker
replicas, one Ceph connector and Traefik on each node. Network Orchestrator remains
plan-only; three replicas do not implement tenant network failover.

See [deployment structure](../docs/02-deployment-structure.md) and the
[lab runbook](../docs/05-lab-platform.md). `operations/` contains explicit operator
preflight/recovery tools; uncertain command outcomes require investigation.
