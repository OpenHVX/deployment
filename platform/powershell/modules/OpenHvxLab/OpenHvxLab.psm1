function Get-OpenHvxLabStatus {
    [CmdletBinding()]
    param()

    $status = [ordered]@{
        RoleInstalled = $false
        HyperVService = $null
        Timestamp = (Get-Date).ToString('o')
    }

    $feature = Get-WindowsFeature -Name Hyper-V -ErrorAction SilentlyContinue
    if ($feature -and $feature.Installed) {
        $status.RoleInstalled = $true
    }

    $service = Get-Service -Name vmms -ErrorAction SilentlyContinue
    if ($service) {
        $status.HyperVService = $service.Status
    }

    return [pscustomobject]$status
}
