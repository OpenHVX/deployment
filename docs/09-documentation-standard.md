# Documentation standard

**Type:** Reference

**Status:** Current

**Scope:** Documentation maintained in the deployment repository

[Documentation index](index.md)

## Language and style

Write maintained documentation in English, matching the repository. Use sentence
case headings, ISO dates (`YYYY-MM-DD`), explicit units (`GiB`, `MiB`, `vCPU`),
relative Markdown links and fenced command blocks with a language. Use consistent
terms: Hyper-V host, infrastructure VM, Network Orchestrator, management network,
source of truth and tenant. Preserve code identifiers exactly.

Lead with the document's purpose and scope. Describe concrete behavior. Distinguish
implemented behavior, recorded verification and planned work. Do not describe an
old planning checklist as the current implementation status.

## Document types

| Type | Content | Required structure |
| --- | --- | --- |
| Runbook | An operational task | Purpose/scope, prerequisites, configuration where needed, procedure, verification, recovery or limitations, related documents |
| Reference | Stable facts or contracts | Scope, organized reference sections, relevant examples and related documents |
| Design | Decisions and planned architecture | Status, problem, design, tradeoffs, delivery/validation criteria |
| Validation guide | A check and its interpretation | Goal, prerequisites, commands, expected result and failure interpretation |
| Status | Supported capabilities and evidence | As-of date, implemented/verified distinction, limits and evidence links |
| Historical record | Past decisions or observations | Archived status, original dates and link to current documentation |

Use these sections where they help the task; do not add empty sections to satisfy
a template. Repository and component READMEs remain short entry points and link
to detailed documents instead of repeating them.

## File names

Use `index.md` for the documentation entry point. Prefix the other documents with
a two-digit reading-order number and a hyphen: `01-status.md`,
`02-deployment-structure.md`, and so on. Historical records have their own numbered
sequence under `history/`. Keep repository and component `README.md` entry points.
Update incoming links whenever a file is renamed.

## Document header

Detailed documents begin with one H1, followed by their type, status, scope and a
link to the documentation index. Record an acceptance date only when evidence
supports it. A documentation edit date does not establish a new verification date.

```markdown
# Topic

**Type:** Runbook
**Status:** Current; acceptance recorded on YYYY-MM-DD
**Scope:** Resources affected by this procedure

[Documentation index](index.md)
```

Adjust the relative index link for nested directories. Historical records may
retain their original structure below the archive notice.

## Commands and evidence

State the working directory, prerequisites and effect of a command before asking
an operator to run it. Separate inspection, image construction, deployment and
destruction. Use explicit placeholders such as `DEPLOYMENT_UUID`; explain where
they come from. Never include real passwords, tokens, private keys or rendered
Kubernetes Secrets.

Give the expected result and the evidence path for a verification command. State
what it does not prove when that limitation matters. Keep destructive commands in
the relevant recovery/lifecycle procedure with existing ownership requirements.

## Source ownership and maintenance

The [documentation index](index.md) is the navigation entry point.
[Current status](01-status.md) summarizes capabilities; runbooks own procedures;
[repository structure](02-deployment-structure.md) owns the directory map. Link to the
owning document instead of copying its full contents.

Update affected procedures with implementation changes. Move superseded narratives
into `history/` when they obscure current instructions, preserving evidence and
adding an archive notice. Check local links, command names, configuration paths,
heading structure and Git whitespace checks before completing an edit.
