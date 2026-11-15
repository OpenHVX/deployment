param(
  [Parameter(Mandatory)][ValidatePattern('^openhvx-vyos-[0-9]{2}$')][string]$Name,
  [Parameter(Mandatory)][guid]$DeploymentId
)
$ErrorActionPreference = 'Stop'
$Ansible.Changed = $false
$folder = "C:\OpenHVX\Network\$Name"
$markerPath = Join-Path $folder 'managed.json'
foreach ($path in @('C:\OpenHVX','C:\OpenHVX\Network',$folder)) {
  if ((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Reparse point refused: $path" }
}
$vm = Get-VM -Name $Name -ErrorAction SilentlyContinue
$marker = if (Test-Path -LiteralPath $markerPath) { Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json } else { $null }
$managed = $marker -and $marker.managedBy -eq 'openhvx-deployment' -and $marker.role -eq 'vyos' -and $marker.deploymentId -eq $DeploymentId.ToString() -and $marker.name -eq $Name -and $marker.hostName -eq $env:COMPUTERNAME
if ($vm) {
  $notes = try { $vm.Notes | ConvertFrom-Json } catch { $null }
  $managed = $managed -and $marker.vmId -eq $vm.Id.ToString() -and $notes.deploymentId -eq $DeploymentId.ToString() -and $notes.role -eq 'vyos'
}
[pscustomobject]@{
  Name=$Name
  VmId=if($vm){$vm.Id.ToString()}elseif($marker){$marker.vmId}else{$null}
  State=if($vm){$vm.State.ToString()}else{'absent'}
  Managed=[bool]$managed
  DeploymentId=$DeploymentId.ToString()
  DiskPresent=Test-Path -LiteralPath (Join-Path $folder 'system.vhdx')
  Snapshots=if($vm){@(Get-VMSnapshot -VM $vm).Count}else{0}
}
