# Executed as SYSTEM during Windows specialize, before any interactive logon.
$ErrorActionPreference = 'Stop'
$media = Split-Path -Parent $PSCommandPath
$config = Get-Content (Join-Path $media 'host.json') -Raw | ConvertFrom-Json
Start-Transcript -Path "$env:WINDIR\Temp\openhvx-bootstrap.log" -Append
try {
    pnputil.exe /add-driver "$media\`$WinPEDriver`$\*.inf" /subdirs /install
    if ($LASTEXITCODE -notin @(0, 259, 3010)) { throw "Installation VirtIO échouée : $LASTEXITCODE" }
    # pnputil returns 259 when every requested package is already installed.
    $devices = @(Get-CimInstance Win32_PnPEntity -Filter "Service='viostor' OR Service='netkvm'")
    if ($devices.Count -lt 2 -or @($devices | Where-Object ConfigManagerErrorCode -ne 0).Count -gt 0) {
        throw 'Les périphériques VirtIO stockage/réseau ne sont pas opérationnels.'
    }
    $pfxPassword = ConvertTo-SecureString $config.pfx_password -AsPlainText -Force
    $certificate = Import-PfxCertificate -FilePath "$media\server.pfx" -CertStoreLocation Cert:\LocalMachine\My -Password $pfxPassword
    Import-Certificate -FilePath "$media\ca.cer" -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
    Set-Service WinRM -StartupType Automatic
    Start-Service WinRM
    # Register PowerShell remoting endpoints without opening HTTP firewall rules.
    Enable-PSRemoting -SkipNetworkProfileCheck -Force
    Get-ChildItem WSMan:\localhost\Listener | Remove-Item -Recurse -Force
    New-Item WSMan:\localhost\Listener -Transport HTTPS -Address '*' -CertificateThumbPrint $certificate.Thumbprint -Force | Out-Null
    Set-Item WSMan:\localhost\Service\Auth\Basic -Value $false
    Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $false
    Get-NetFirewallRule -Name 'WINRM-HTTP-In-TCP*' -ErrorAction SilentlyContinue | Disable-NetFirewallRule
    New-NetFirewallRule -Name OpenHVX-WinRM-HTTPS -DisplayName OpenHVX-WinRM-HTTPS -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5986 -RemoteAddress $config.management_cidr -Profile Any | Out-Null
} finally { Stop-Transcript }
