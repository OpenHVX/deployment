# Unattended Windows installation

**Type:** Runbook

**Status:** Current

**Scope:** Provision blank Windows lab disks and resume bootstrap

[Documentation index](index.md)

## Purpose

Prepare Windows installation media and provision the simulated Hyper-V hosts.
Platform deployment follows the separate [lab deployment procedure](05-lab-platform.md).

## Prerequisites

Provide a Windows Server ISO and install the workstation tools listed below.
Run all commands from the repository root.

Installation targets **blank disks**: Windows Setup uses the answer file to erase
disk 0. Never boot a disk containing data to retain from this media.
An already installed Windows disk keeps boot priority.

## Configuration

Provide the Windows ISO through `os_iso_path` in `tofu/environments/lab/lab.auto.tfvars`.
`mise run windows:prepare`:

- Downloads the stable VirtIO ISO once from Fedora, or uses `LAB_VIRTIO_ISO`,
  an absolute path to a locally supplied ISO.
- Uses `2k25/amd64` drivers by default; override with
  `LAB_VIRTIO_WINDOWS_VERSION=2k22` for Server 2022.
- Defaults to WIM index **4**. Check edition ordering in your ISO; override with
  `LAB_WINDOWS_IMAGE_INDEX`.
- Generates a local CA and per-host certificates with IP/DNS SANs.
- Creates a per-host answer ISO containing hostname, password, and drivers.
- Rebuilds a UEFI ISO from the supplied media using `efisys_noprompt.bin` to
  remove the keyboard prompt at DVD boot.
- Writes `zz-unattended.auto.tfvars.json`, a generated local ISO-path override.

Required system tools: `7z`, `xorriso`, `openssl`, `curl`, and `setfacl`.
They are not installed automatically. The QEMU account defaults to `libvirt-qemu`;
set `LAB_QEMU_USER` to override it. ACLs grant only that account access to private
media. Allow approximately 25 GiB of temporary space for preparation.

## Procedure

```bash
mise install
mise run bootstrap
mise run lab:hosts:up
```

`lab:hosts:up` prepares media, reviews/applies the OpenTofu plan and waits for
WinRM. Use `mise run windows:prepare` to prepare media without provisioning hosts.

## Secrets and trust

Media and keys remain under Git-ignored `.lab/`, with private permissions.
The generated Administrator secret stays in `.lab/windows-password`, not in
OpenTofu variables or state. ISOs do contain the Setup secret and must therefore
be treated as secrets. Ansible wrappers load the secret and `.lab/ca.pem`
automatically. Do not enable shell tracing or print answer files.

`lab/windows/Initialize-LabWindows.ps1` runs during `specialize` without an
interactive session. It installs drivers, configures WinRM HTTPS, removes the
HTTP listener, disables Basic and unencrypted traffic, and restricts the HTTPS
firewall rule to the management CIDR. The Windows role removes cached answer
files after the first authenticated connection.

Windows bootstrap logs: `C:\Windows\Temp\openhvx-bootstrap.log`.
Setup logs: `C:\Windows\Panther`. Open the console for diagnosis after a failure.
Windows updates are not yet orchestrated. Agent installation belongs to the later
platform deployment step. Ansible configures Hyper-V after Windows bootstrap. `test:lab` starts and deletes a
temporary L2 VM per host without a guest OS; it proves the nested engine, not
guest OS operation or the OpenHVX API.

## Verification

`test:lab` creates, starts and removes a temporary diskless Hyper-V VM on each host.
This verifies nested startup, not guest networking or platform availability.

## Recovery

Preparation reuses unchanged media. It refuses to replace an answer ISO whose
parameters have changed. To rebuild one, first stop the affected VMs and detach
the media, then remove the ISO and its `.lab/media/lab-hvNN.json` manifest before
running `windows:prepare`. Keep the secret and CA for existing Windows installations.

After successful installation, resume configuration and validate the nested engine:

```bash
mise run ansible:bootstrap
mise run ansible:configure
mise run test:lab
```

## Limitations

Windows Failover Clustering and tenant VM HA are not configured by this procedure.


## References

- https://learn.microsoft.com/windows-hardware/manufacture/desktop/windows-setup-automation-overview
- https://learn.microsoft.com/windows-hardware/manufacture/desktop/add-device-drivers-to-windows-during-windows-setup
- https://github.com/virtio-win/virtio-win-pkg-scripts
