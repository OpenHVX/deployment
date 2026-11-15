param(
  [Parameter(Mandatory)][ValidatePattern('^openhvx-vyos-[0-9]{2}$')][string]$Name,
  [Parameter(Mandatory)][guid]$DeploymentId,
  [Parameter(Mandatory)][string]$ImageUrl,
  [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string]$ImageSha256,
  [Parameter(Mandatory)][string]$SeedUrl,
  [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string]$SeedSha256,
  [Parameter(Mandatory)][ValidatePattern('^[0-9A-Fa-f]{12}$')][string]$MacAddress,
  [string]$SwitchName = 'OpenHVX-Management',
  [ValidateRange(4,64)][int]$SystemGiB = 10
)
$ErrorActionPreference = 'Stop'
$Ansible.Changed = $false
$root = 'C:\OpenHVX\Network'
$folder = Join-Path $root $Name
$markerPath = Join-Path $folder 'managed.json'
$disk = Join-Path $folder 'system.vhdx'
$seed = Join-Path $folder 'seed.iso'
foreach ($path in @('C:\OpenHVX',$root,$folder)) {
  if ((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Reparse point refused: $path" }
}
$vm = Get-VM -Name $Name -ErrorAction SilentlyContinue
$marker = $null
if (Test-Path -LiteralPath $markerPath) {
  $marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
  if ($marker.managedBy -ne 'openhvx-deployment' -or $marker.role -ne 'vyos' -or $marker.deploymentId -ne $DeploymentId.ToString() -or $marker.name -ne $Name -or $marker.hostName -ne $env:COMPUTERNAME) { throw 'Ownership marker mismatch' }
  if ($marker.imageSha256 -ne $ImageSha256 -or $marker.seedSha256 -ne $SeedSha256 -or $marker.systemGiB -ne $SystemGiB -or $marker.macAddress -ne $MacAddress -or $marker.switchName -ne $SwitchName) { throw 'Declaration changed; use an explicit maintenance/rebuild workflow' }
}
if ($vm) {
  if (!$marker -or !$marker.vmId -or $vm.Id.ToString() -ne $marker.vmId) { throw 'Existing VM is not owned by this deployment' }
  $ownership = $vm.Notes | ConvertFrom-Json
  if ($ownership.deploymentId -ne $DeploymentId.ToString() -or $ownership.role -ne 'vyos') { throw 'VM annotation mismatch' }
  $disks = @(Get-VMHardDiskDrive -VM $vm)
  $nics = @(Get-VMNetworkAdapter -VM $vm)
  if ($vm.Generation -ne 2 -or $vm.MemoryStartup -ne 2GB -or $vm.ProcessorCount -ne 2 -or $vm.DynamicMemoryEnabled) { throw 'Existing VM hardware differs' }
  if ($disks.Count -ne 1 -or $disks[0].Path -ne $disk -or (Get-VHD -Path $disk).Size -ne ($SystemGiB * 1GB)) { throw 'Existing VM disk differs' }
  if ($nics.Count -ne 1 -or $nics[0].SwitchName -ne $SwitchName -or $nics[0].MacAddress -ne $MacAddress) { throw 'Existing VM management NIC differs' }
  if (!(Test-Path -LiteralPath $seed) -or (Get-FileHash -LiteralPath $seed -Algorithm SHA256).Hash -ne $SeedSha256) { throw 'Existing seed differs' }
  if ($vm.State -eq 'Off') { Start-VM -VM $vm; $Ansible.Changed = $true }
  elseif ($vm.State -ne 'Running') { throw "Unexpected VM state: $($vm.State)" }
  [pscustomobject]@{Name=$Name;VmId=$vm.Id.ToString();State=(Get-VM -Id $vm.Id).State.ToString();Changed=$Ansible.Changed}
  return
}
if ($marker -and $marker.vmId) { throw 'Owned VM disappeared; inspect or destroy its retained disks before recreating' }
if ((Test-Path -LiteralPath $folder) -and !$marker) { throw 'Unowned VM directory exists' }
if (Test-Path -LiteralPath $disk) { throw 'Partially prepared disk exists; inspect then use targeted destruction before retrying' }
if (!(Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue)) { throw 'Management switch must already exist; router deployment never changes host uplinks' }
$freeBytes = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory * 1KB
if ($freeBytes -lt 3GB) { throw 'At least 3 GiB free host RAM required (2 GiB guest plus 1 GiB headroom)' }
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$Ansible.Changed = $true
$marker = [ordered]@{managedBy='openhvx-deployment';role='vyos';deploymentId=$DeploymentId.ToString();name=$Name;hostName=$env:COMPUTERNAME;vmId=$null;imageSha256=$ImageSha256;seedSha256=$SeedSha256;systemGiB=$SystemGiB;macAddress=$MacAddress;switchName=$SwitchName;phase='preparing'}
function Save-Marker { $marker | ConvertTo-Json | Set-Content -LiteralPath "$markerPath.partial" -Encoding UTF8; Move-Item -LiteralPath "$markerPath.partial" -Destination $markerPath -Force }
Save-Marker
$cache = Join-Path $root "vyos-$ImageSha256.vhdx"
if (!(Test-Path -LiteralPath $cache)) {
  Invoke-WebRequest -UseBasicParsing -Uri $ImageUrl -OutFile "$cache.partial"
  if ((Get-FileHash -LiteralPath "$cache.partial" -Algorithm SHA256).Hash -ne $ImageSha256) { throw 'Image checksum mismatch' }
  Move-Item -LiteralPath "$cache.partial" -Destination $cache
}
if ((Get-FileHash -LiteralPath $cache -Algorithm SHA256).Hash -ne $ImageSha256) { throw 'Cached image checksum mismatch' }
if ((Get-VHD -Path $cache).Size -gt ($SystemGiB * 1GB)) { throw 'Image exceeds declared disk size' }
Invoke-WebRequest -UseBasicParsing -Uri $SeedUrl -OutFile "$seed.partial"
if ((Get-FileHash -LiteralPath "$seed.partial" -Algorithm SHA256).Hash -ne $SeedSha256) { throw 'Seed checksum mismatch' }
Move-Item -LiteralPath "$seed.partial" -Destination $seed -Force
Copy-Item -LiteralPath $cache -Destination $disk
if ((Get-VHD -Path $disk).Size -lt ($SystemGiB * 1GB)) { Resize-VHD -Path $disk -SizeBytes ($SystemGiB * 1GB) }
$vm = New-VM -Name $Name -Generation 2 -MemoryStartupBytes 2GB -VHDPath $disk -Path $folder -SwitchName $SwitchName
$marker.vmId = $vm.Id.ToString()
Save-Marker
Set-VM -VM $vm -Notes (@{managedBy='openhvx-deployment';role='vyos';deploymentId=$DeploymentId.ToString()} | ConvertTo-Json -Compress) -AutomaticStartAction Start -AutomaticStopAction ShutDown -AutomaticCheckpointsEnabled $false
Set-VMProcessor -VM $vm -Count 2
Set-VMMemory -VM $vm -DynamicMemoryEnabled $false
Set-VMFirmware -VM $vm -EnableSecureBoot Off
Get-VMNetworkAdapter -VM $vm | Set-VMNetworkAdapter -StaticMacAddress $MacAddress
Set-VMComPort -VMName $Name -Number 1 -Path "\\.\pipe\OpenHVX-$Name"
Add-VMDvdDrive -VM $vm -Path $seed
$marker.phase = 'created'
Save-Marker
Start-VM -VM $vm
$Ansible.Changed = $true
[pscustomobject]@{Name=$Name;VmId=$vm.Id.ToString();State=(Get-VM -Id $vm.Id).State.ToString();Changed=$true}
