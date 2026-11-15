# Exécuter en administrateur dans lab-hv01 après installation/redémarrage Hyper-V.
# Ne touche jamais une VM existante. Le test prouve le démarrage du moteur L2,
# sans prétendre tester un OS invité ni l'API OpenHVX.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$name = 'openhvx-capability-' + [guid]::NewGuid().ToString('N')
try {
    New-VM -Name $name -Generation 2 -MemoryStartupBytes 2GB -NoVHD | Out-Null
    Set-VMProcessor -VMName $name -Count 2
    Start-VM -Name $name
    Start-Sleep -Seconds 5
    $vm = Get-VM -Name $name
    if ($vm.State -ne 'Running') { throw "La VM L2 n'est pas Running : $($vm.State)" }
    [pscustomobject]@{ Name = $name; State = $vm.State; CapabilityPassed = $true }
} finally {
    if (Get-VM -Name $name -ErrorAction SilentlyContinue) {
        Stop-VM -Name $name -TurnOff -Force -ErrorAction SilentlyContinue
        Remove-VM -Name $name -Force
    }
}
