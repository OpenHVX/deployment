# Deployment documentation

Start with the document for the task you want to perform. Commands run from the
`deployment` repository root unless a procedure explicitly says otherwise.
Current documents describe the supported workflow; historical records preserve
past decisions and evidence without defining present behavior.

## Guides and references

| Task | Document | Type |
| --- | --- | --- |
| Install the lab and access K3s/OpenHVX | [Lab setup and access](10-lab-setup-and-access.md) | Runbook |
| Understand what is implemented and verified | [Current status](01-status.md) | Status |
| Find the source file to modify | [Repository structure](02-deployment-structure.md) | Reference |
| Deploy and operate the lab platform | [Lab deployment](05-lab-platform.md) | Runbook |
| Install Windows on blank lab disks | [Windows installation](04-unattended-windows.md) | Runbook |
| Validate nested virtualization | [Nested virtualization](03-nested-virtualization.md) | Validation guide |
| Build, deploy, inspect or remove routers | [VyOS lifecycle](06-vyos-lifecycle.md) | Runbook |
| Deploy and inspect logical VPC planning | [Network PoC](07-network-poc.md) | Runbook |
| Inspect Kubernetes sources and private rendering | [Kubernetes resources](../kubernetes/README.md) | Component reference |
| Find the VyOS image factory | [VyOS image](../image-builds/vyos/README.md) | Component reference |
| Maintain scripts/playbooks and recover deployments | [Maintaining deployment](11-maintaining-deployment.md) | Reference |
| Write or update documentation | [Documentation standard](09-documentation-standard.md) | Reference |

## Historical records

- [Original K3s design](08-openhvx-k3s.md): initial architecture and delivery checklist.
- [Lab implementation history](history/02-lab-status-2026-11-14.md): dated observations and acceptance records.
- [Initial project context](history/01-lab-context.md): earlier decisions and implementation notes.

## Evidence and source of truth

Versioned configuration declares the intended infrastructure. Runtime files under
`.lab/` contain private credentials, deployment identities and acceptance evidence;
they are not documentation to paste into issues. OpenTofu state records resource
identities. OpenHVX remains the source of truth for tenant resources.

A recorded successful test is evidence for its stated scope and date. It is not a
live health check or proof of production availability. Use the relevant runbook's
verification procedure to inspect the present lab.
