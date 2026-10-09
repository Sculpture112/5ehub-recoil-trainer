param(
    [ValidateSet('Install', 'Restore', 'Check')][string]$Action = 'Install',
    [string]$TargetPath
)
$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'patch-lib.ps1')
    Invoke-MapPatch -PackageRoot $PSScriptRoot -TargetPath $TargetPath -Action $Action
    exit 0
}
catch {
    if (Get-Command Write-PatchFailure -ErrorAction SilentlyContinue) { Write-PatchFailure $_ }
    else { Write-Host "操作未完成 [INSTALLER_SCRIPT_ERROR]：$($_.Exception.Message)" -ForegroundColor Red; Write-Host '安装脚本缺失或无法读取，请重新完整解压补丁。' }
    exit 1
}
