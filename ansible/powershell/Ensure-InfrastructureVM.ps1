param(
  [Parameter(Mandatory)][string]$Name,
  [Parameter(Mandatory)][string]$ImageUrl,
  [Parameter(Mandatory)][string]$ImageSha256,
  [Parameter(Mandatory)][string]$SeedUrl,
  [Parameter(Mandatory)][string]$SeedSha256,
  [string]$Root = 'C:\OpenHVX\Infrastructure',
  [string]$SwitchName = 'OpenHVX-Management',
  [ValidatePattern('^[a-zA-Z0-9_-]+\.vhdx$')][string]$ImageCacheName = 'ubuntu-base.vhdx',
  [bool]$VerifyExistingSeed = $false,
  [int]$MemoryGiB = 8,
  [int]$Cpu = 4,
  [int]$SystemGiB = 40,
  [bool]$ResumePreparedDisk = $false,
  [int]$DataGiB = 0
)
$ErrorActionPreference = 'Stop'
$Ansible.Changed = $false
$vm = Get-VM -Name $Name -ErrorAction SilentlyContinue
if ($vm) {
  if ($VerifyExistingSeed) {
    $existingSeed = "$Root\$Name\seed.iso"
    if (!(Test-Path $existingSeed) -or (Get-FileHash $existingSeed -Algorithm SHA256).Hash -ne $SeedSha256) {
      throw 'Existing bootstrap seed differs; explicit guest configuration or rebuild is required'
    }
  }
  if ($vm.Generation -ne 2) { throw "Existing $Name has an incompatible generation" }
  if ($vm.MemoryStartup -ne ($MemoryGiB * 1GB) -or $vm.ProcessorCount -ne $Cpu) {
    throw "Existing $Name sizing differs; explicit offline resizing is required"
  }
  if ($DataGiB -gt 0 -and !(Get-VMHardDiskDrive -VMName $Name | Where-Object Path -eq "$Root\$Name\data.vhdx")) {
    throw "Existing $Name is missing its managed data disk; refusing implicit repair"
  }
  $system = Get-VMHardDiskDrive -VMName $Name | Where-Object Path -eq "$Root\$Name\system.vhdx"
  if (!$system -or (Get-VHD -Path $system.Path).Size -ne ($SystemGiB * 1GB)) { throw 'Existing system disk differs from the declaration' }
  if (!(Get-VMNetworkAdapter -VMName $Name | Where-Object SwitchName -eq $SwitchName)) { throw 'Existing management switch attachment differs' }
  if ($vm.State -eq 'Off') { Start-VM $Name | Out-Null; $Ansible.Changed = $true }
  return
}
$nic = Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -like '*VirtIO*' } | Select-Object -First 1
if (!(Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue)) {
  if (!$nic) { throw 'No active VirtIO adapter found; set up a management vSwitch explicitly on physical hosts' }
  New-VMSwitch -Name $SwitchName -NetAdapterName $nic.Name -AllowManagementOS $true | Out-Null
  $Ansible.Changed = $true
}
$folder = "$Root\$Name"
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$cache = "$Root\$ImageCacheName"
if (!(Test-Path $cache)) {
  Invoke-WebRequest -UseBasicParsing -Uri $ImageUrl -OutFile "$cache.partial"
  if ((Get-FileHash "$cache.partial" -Algorithm SHA256).Hash -ne $ImageSha256) { throw 'Base image checksum mismatch' }
  Move-Item "$cache.partial" $cache
}
if ((Get-FileHash $cache -Algorithm SHA256).Hash -ne $ImageSha256) { throw 'Cached image checksum mismatch' }
$disk = "$folder\system.vhdx"
if (Test-Path $disk) {
  if (!$ResumePreparedDisk) { throw "Orphaned system disk at $disk; inspect manually before adopting" }
  if (Get-VM | Get-VMHardDiskDrive | Where-Object Path -eq $disk) { throw 'Prepared disk already attached' }
} else { Copy-Item $cache $disk }
Resize-VHD -Path $disk -SizeBytes ($SystemGiB * 1GB)
Invoke-WebRequest -UseBasicParsing -Uri $SeedUrl -OutFile "$folder\seed.iso"
if ((Get-FileHash "$folder\seed.iso" -Algorithm SHA256).Hash -ne $SeedSha256) { throw 'Seed checksum mismatch' }
New-VM -Name $Name -Generation 2 -MemoryStartupBytes ($MemoryGiB * 1GB) -VHDPath $disk -Path $folder -SwitchName $SwitchName | Out-Null
Set-VMProcessor -VMName $Name -Count $Cpu
Set-VMMemory -VMName $Name -DynamicMemoryEnabled $false
Set-VMFirmware -VMName $Name -EnableSecureBoot Off
Add-VMDvdDrive -VMName $Name -Path "$folder\seed.iso"
if ($DataGiB -gt 0) {
  if (Test-Path "$folder\data.vhdx") { throw 'Refusing to replace existing data disk' }
  New-VHD -Path "$folder\data.vhdx" -Dynamic -SizeBytes ($DataGiB * 1GB) | Out-Null
  Add-VMHardDiskDrive -VMName $Name -Path "$folder\data.vhdx"
}
Set-VM -Name $Name -AutomaticStartAction Start -AutomaticStopAction ShutDown
Start-VM $Name | Out-Null
$Ansible.Changed = $true
