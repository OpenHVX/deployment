# Nested virtualization validation

## Goal

Before implementing the lab, verify that the Linux host supports nested KVM and
that a level-1 Windows Server VM can run Hyper-V and a level-2 VM.

## Minimum checklist

- CPU with VT-x/EPT or AMD-V/NPT
- `kvm_intel` or `kvm_amd` module loaded
- Accessible `/dev/kvm`
- KVM module nesting enabled
- Working libvirt
- Windows Server VM booted in a compatible mode (host-passthrough or default virt-type)
- Hyper-V role installed
- Level-2 test VM started and observed

## Recommended commands

```bash
sudo ls -l /dev/kvm
sudo modinfo kvm_intel | grep -i nested
cat /sys/module/kvm_intel/parameters/nested
sudo virsh -c qemu:///system version
```

Replace `kvm_intel` with `kvm_amd` when using the AMD module.

## Expected outcome

- Nesting reports `Y` or `1`.
- The level-1 Windows VM boots.
- Hyper-V is enabled.
- A level-2 VM starts on the Hyper-V host.

## Blocking failures

If any check fails, suspend automation and document the exact CPU, kernel, and
libvirt configuration.

## Observations on November 7, 2026

- Workstation: Arch Linux x86-64, kernel 6.19.14-arch1-1.
- CPU: AMD Ryzen Threadripper PRO 3995WX, 64 cores / 128 threads, svm and npt.
- RAM: 251 GiB total, approximately 228 GiB available during diagnostics.
- Storage: approximately 1972 GiB available on the libvirt image volume.
- Accessible `/dev/kvm`; `kvm_amd/parameters/nested = 1`.
- Successful user connection to `qemu:///system`, libvirt 12.2.0 / QEMU 11.0.0.
- Existing networks: LAN 192.168.0.0/24, libvirt 192.168.100.0/24,
  Docker 172.17 through 172.20.0.0/16. No observed overlap with 192.168.50.0/24.
- Five existing VMs running, left unchanged.
- Windows ISO unavailable: Windows/Hyper-V/L2 **not tested** at that time.

## Test to run in Windows Server

Install the role from an administrator PowerShell console, then restart:

```powershell
Install-WindowsFeature -Name Hyper-V -IncludeManagementTools -Restart
```

After reboot, copy and run `platform/powershell/Test-NestedHyperV.ps1`.
It creates a uniquely named generation-2 VM, attempts to start it, and removes it
in a `finally` block. This proves only that the Hyper-V engine starts, not that a
guest OS boots. Follow up with a small VM containing a guest OS and record its
boot. The presence of the Windows role alone is not evidence of success.

Record Windows version/edition, reboot outcome, script output, L2 guest OS,
Running state, relevant Hyper-V events, and the decision to continue with KVM
or evaluate native Hyper-V.

## Unattended deployment results across all three hosts

Windows Server 2025 (build 26100) was installed without interaction on lab-hv01,
lab-hv02, and lab-hv03, with VirtIO drivers and individual hostnames.
WinRM HTTPS authenticated on all three using a local CA and IP SAN certificates.
Hyper-V was installed and the hosts rebooted automatically.
`mise run test:lab` created, started (Running), and deleted a diskless generation-2
L2 VM on each host: zero failures.
This validates the nested Hyper-V engine. L2 guest OS boot, tenant networking,
the OpenHVX API, and HCI storage still need testing.
The earlier “ISO unavailable / not tested” observation is historical.
