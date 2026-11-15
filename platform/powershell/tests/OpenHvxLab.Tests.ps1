$modulePath = Join-Path $PSScriptRoot '..\modules\OpenHvxLab\OpenHvxLab.psm1'
Import-Module $modulePath -Force

Describe 'OpenHvxLab' {
  It 'exposes a status object' {
    $result = Get-OpenHvxLabStatus
    $result | Should -Not -BeNullOrEmpty
    $result.Timestamp | Should -Not -BeNullOrEmpty
  }
}
