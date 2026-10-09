param([string]$GamePath, [string]$TargetPath)
$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'patch-lib.ps1')
    $script:PatchPhase = '启动前检查补丁包'
    Write-Host '[启动 1/3] 检查补丁包与辅助程序……'
    $manifest = Read-PatchManifest $PSScriptRoot
    if (-not $manifest.PSObject.Properties['helper']) {
        Throw-PatchIssue 'PACKAGE_MANIFEST_INVALID' '当前补丁包没有训练辅助程序信息。' @() '请使用包含启动训练和 helper 文件夹的完整整合包。'
    }
    $helper = Join-Path $PSScriptRoot 'helper\5EHubAssist.exe'
    Assert-Digest $helper $manifest.helper.sha256 'Package'
    Write-Host '[启动 2/3] 检查地图版本与已安装补丁……'
    $target = Resolve-MapTarget $TargetPath
    Assert-MapBaseline $target $manifest
    $script:PatchPhase = '检查补丁是否已安装到当前地图'
    Assert-Digest (Join-Path $target $script:DirName) $manifest.patchDirSha256 'Installed'
    Assert-Digest (Join-Path $target $script:DataName) $manifest.patchDataSha256 'Installed'
    Write-Host '[启动 3/3] 检查游戏位置与启动参数……'
    $script:PatchPhase = '检查游戏位置与启动参数'
    if (-not $GamePath) {
        $games = @(Get-SteamLibraries | ForEach-Object {
            $candidate = Join-Path $_ 'steamapps\common\Counter-Strike Global Offensive\game\bin\win64\cs2.exe'
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { (Get-Item -LiteralPath $candidate).FullName }
        } | Sort-Object -Unique)
        if ($games.Count -eq 0) { Throw-PatchIssue 'GAME_NOT_FOUND' '未找到 CS2 安装位置。' @() '先通过 Steam 确认 CS2 已安装，再运行启动训练。' }
        if ($games.Count -gt 1) { Throw-PatchIssue 'GAME_PATH_AMBIGUOUS' '检测到多份 CS2，无法确定启动哪一份。' $games '保留正确的游戏安装路径，或发送以上路径以明确配置。' }
        $GamePath = $games[0]
    }
    if (-not (Test-Path -LiteralPath $GamePath -PathType Leaf)) { Throw-PatchIssue 'GAME_NOT_FOUND' '指定的 CS2 程序不存在。' @($GamePath) '先确认游戏已安装，并使用正确的游戏路径。' }
    $GamePath = (Get-Item -LiteralPath $GamePath -ErrorAction Stop).FullName
    if ([IO.Path]::GetFileName($GamePath) -ne 'cs2.exe') { Throw-PatchIssue 'GAME_PATH_INVALID' '指定程序不是 cs2.exe。' @($GamePath) '使用正确的 CS2 游戏程序路径。' }
    $running = @(Get-CimInstance Win32_Process -Filter "Name='cs2.exe'")
    if ($running.Count -gt 0) {
        if ($running.Count -ne 1 -or $running[0].ExecutablePath -ne $GamePath -or $running[0].CommandLine -notmatch '(?i)(?:^|\s)-vconport\s+29000(?:\s|$)') {
            Throw-PatchIssue 'GAME_LAUNCH_MISMATCH' '当前运行的 CS2 与训练启动位置或参数不匹配。' @('训练需要本机控制台参数：-vconport 29000') '退出 CS2 后，使用本补丁文件夹的启动训练.cmd；它会自动带上所需参数。'
        }
        Write-Host '游戏已运行，将连接辅助程序；请打开原版 5EHub。'
    }
    else {
        $script:PatchPhase = '启动 CS2'
        Start-Process -FilePath $GamePath -WorkingDirectory ([IO.Path]::GetDirectoryName($GamePath)) -ArgumentList '-steam -worldwide -insecure -novid -console -vconport 29000 +map 5e_aimhub customgamemode=3086023598 nomapvalidation=true' -WindowStyle Hidden
    }
    $script:PatchPhase = '启动后台辅助程序'
    Start-Process -FilePath $helper -ArgumentList '--wait-console 90' -WindowStyle Hidden
    Write-Host '已发起训练启动。后台程序将等待游戏连接，最长 90 秒。' -ForegroundColor Green
    Write-Host '此处只确认启动请求已发出；游戏内轨迹是否显示仍需进入闪身模式确认。'
    Write-Host '双 Tab → 自瞄与目标，可切换绘制版本和显示时机。'
    Write-Host '辅助程序在后台运行，退出游戏后自动结束；无需安装额外环境。'
    exit 0
}
catch {
    if (Get-Command Write-PatchFailure -ErrorAction SilentlyContinue) { Write-PatchFailure $_ }
    else { Write-Host "启动未完成 [INSTALLER_SCRIPT_ERROR]：$($_.Exception.Message)" -ForegroundColor Red; Write-Host '启动脚本缺失或无法读取，请重新完整解压补丁。' }
    exit 1
}
