param(
  [Parameter(Mandatory)][ValidatePattern('^openhvx-vyos-[0-9]{2}$')][string]$Name,
  [Parameter(Mandatory)][guid]$DeploymentId,
  [bool]$Apply = $false
)
$ErrorActionPreference = 'Stop'
$Ansible.Changed = $false
$folder = "C:\OpenHVX\Network\$Name"
$markerPath = Join-Path $folder 'managed.json'
$disk = Join-Path $folder 'system.vhdx'
foreach ($path in @('C:\OpenHVX','C:\OpenHVX\Network',$folder)) {
  if ((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Reparse point refused: $path" }
}
$vm = Get-VM -Name $Name -ErrorAction SilentlyContinue
if (!(Test-Path -LiteralPath $markerPath)) {
  if ($vm -or (Test-Path -LiteralPath $folder)) { throw 'Refusing to remove an unowned VM or directory' }
  [pscustomobject]@{Name=$Name;State='absent';Apply=$Apply}
  return
}
$marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
if ($marker.managedBy -ne 'openhvx-deployment' -or $marker.role -ne 'vyos' -or $marker.deploymentId -ne $DeploymentId.ToString() -or $marker.name -ne $Name -or $marker.hostName -ne $env:COMPUTERNAME) { throw 'Ownership marker mismatch' }
if ($vm) {
  if (!$marker.vmId -or $vm.Id.ToString() -ne $marker.vmId) { throw 'VM GUID differs; refusing name-based deletion' }
  $notes = $vm.Notes | ConvertFrom-Json
  if ($notes.deploymentId -ne $DeploymentId.ToString() -or $notes.role -ne 'vyos') { throw 'VM annotation mismatch' }
  $disks = @(Get-VMHardDiskDrive -VM $vm)
  if ($disks.Count -ne 1 -or $disks[0].Path -ne $disk) { throw 'Unexpected disk attachment; inspect before destruction' }
  if (@(Get-VMSnapshot -VM $vm).Count) { throw 'Snapshots must be handled explicitly before destruction' }
}
$otherAttachments = @(Get-VM | Where-Object { !$vm -or $_.Id -ne $vm.Id } | Get-VMHardDiskDrive | Where-Object { $_.Path -eq $disk })
if ($otherAttachments.Count) { throw 'Managed disk is attached to another VM' }
# Enumerate without following junctions before any mutation, including preview.
function Get-SafeDirectories([string]$Path) {
  foreach ($directory in @(Get-ChildItem -LiteralPath $Path -Directory -Force)) {
    if ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse point in owned directory' }
    Get-SafeDirectories $directory.FullName
    $directory.FullName
  }
}
$directories = @(Get-SafeDirectories $folder)
$known = @('managed.json','managed.json.partial','system.vhdx','seed.iso','seed.iso.partial')
$unexpected = @(Get-ChildItem -LiteralPath $folder -File -Force | Where-Object { $_.Name -notin $known })
if ($unexpected.Count) { throw 'Unknown files found in managed directory' }
[pscustomobject]@{Name=$Name;VmId=$marker.vmId;Disk=$disk;DeploymentId=$DeploymentId.ToString();Apply=$Apply;State=if($vm){$vm.State.ToString()}else{'definition-absent'}}
if (!$Apply) { return }
if ($vm) {
  if ($vm.State -ne 'Off') { Stop-VM -VM $vm -TurnOff -Force }
  Remove-VM -VM $vm -Force
}
foreach ($name_ in @('system.vhdx','seed.iso','seed.iso.partial','managed.json.partial')) {
  $path = Join-Path $folder $name_
  if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
}
# Remove only empty directories after Hyper-V removes its definition; never recurse-delete files.
foreach ($directory in $directories) {
  if ((Test-Path -LiteralPath $directory) -and !(Get-ChildItem -LiteralPath $directory -Force)) {
    Remove-Item -LiteralPath $directory
  }
}
$remaining = @(Get-ChildItem -LiteralPath $folder -Force | Where-Object Name -ne 'managed.json')
if ($remaining.Count) { throw 'VM removed; unexpected remaining files retained with ownership marker for inspection' }
Remove-Item -LiteralPath $markerPath -Force
Remove-Item -LiteralPath $folder
$Ansible.Changed = $true
