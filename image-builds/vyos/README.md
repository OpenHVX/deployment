# Installed VyOS image

**Type:** Component reference

**Status:** Current

**Scope:** Installed VyOS image construction

Run `mise run lab:network:vyos-image` from the repository root. `build.py` uses the
pinned ISO/checksum catalog in `environments/lab/network/vyos-iso.json` and the
existing QEMU/Pexpect factory. It prepares a reusable installed VHDX with verified
cloud-init support; no Hyper-V host is modified by image construction.

Artifacts, build locks and verification receipts remain private under
`.lab/network/`. Do not commit images or run simultaneous factories against the
same work directory. See [the lifecycle runbook](../../docs/06-vyos-lifecycle.md).
