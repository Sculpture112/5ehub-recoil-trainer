param(
    [string]$ReportPath = (Join-Path $PSScriptRoot '5ehub-support-report.txt'),
    [string]$PackageRoot = '',
    [string[]]$Libraries = @()
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'patch-lib.ps1')
$rows = New-Object 'System.Collections.Generic.List[string]'
function Note([string]$Text) { $rows.Add($Text); Write-Host $Text }
function Field($Object, [string]$Name) {
    if ($null -ne $Object -and $Object.PSObject.Properties[$Name]) { return $Object.PSObject.Properties[$Name].Value }
    return $null
}
function Section([string]$Name, [scriptblock]$Read) {
    Note "`n[$Name]"
    try { & $Read } catch { Note ('读取失败：' + $_.Exception.Message) }
}
function InspectFile([string]$Path, [string]$Expected = '') {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { Note ((Split-Path $Path -Leaf) + '：缺少文件'); return }
    try {
        $before = Get-Item -LiteralPath $Path
        $length = $before.Length; $stamp = $before.LastWriteTimeUtc
        $hash = Get-FileDigest $Path
        $after = Get-Item -LiteralPath $Path
        $stable = $after.Length -eq $length -and $after.LastWriteTimeUtc -eq $stamp
        Note ('{0}：字节={1}，UTC={2:o}，SHA256={3}，采集时稳定={4}' -f $before.Name,$length,$stamp,$hash,$stable)
        if ($Expected) { Note ('  预期=' + $Expected + '；匹配=' + ($hash -eq $Expected)) }
    } catch { Note ('无法读取 ' + (Split-Path $Path -Leaf) + '：' + $_.Exception.Message) }
}
try {
    Note '5EHub 一键检查 v2026.10.09（只读取；不会安装、还原或启动游戏）'
    Note ('采集时间 UTC：' + [DateTime]::UtcNow.ToString('o'))
    $reference = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'known-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $manifest = $reference
    Section '补丁包' {
        if (-not $PackageRoot) {
            foreach ($candidate in @($PSScriptRoot, (Split-Path $PSScriptRoot -Parent))) {
                if (Test-Path -LiteralPath (Join-Path $candidate 'manifest.json')) { $script:PackageRoot = $candidate; break }
            }
        }
        if ($PackageRoot) {
            $script:manifest = Get-Content -LiteralPath (Join-Path $PackageRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
            if ((Field $manifest 'mapId') -ne '3086023598') { throw '补丁包的地图编号不符。' }
            Note ('检测到补丁版本：' + (Field $manifest 'version'))
            InspectFile (Join-Path $PackageRoot 'payload\3086023598_dir.vpk') (Field $manifest 'patchDirSha256')
            InspectFile (Join-Path $PackageRoot 'payload\3086023598_002.vpk') (Field $manifest 'patchDataSha256')
            InspectFile (Join-Path $PackageRoot 'helper\5EHubAssist.exe') (Field (Field $manifest 'helper') 'sha256')
        } else {
            Note ('未找到用户的补丁包。以下文件比对采用参考版本 ' + $reference.version + '，不代表用户安装的版本。')
        }
    }
    if ((Field $manifest 'mapId') -ne '3086023598') { $manifest = $reference }
    if ($Libraries.Count -eq 0) { $Libraries = @(Get-SteamLibraries | Sort-Object -Unique) }
    # Registry and libraryfolders.vdf can spell the same Windows path differently.
    $uniqueLibraries = @()
    foreach ($library in $Libraries) {
        $normalized = [IO.Path]::GetFullPath($library).TrimEnd([char]'\')
        if ($uniqueLibraries -notcontains $normalized) { $uniqueLibraries += $normalized }
    }
    $Libraries = $uniqueLibraries
    $targets = New-Object 'System.Collections.Generic.List[string]'
    Section 'Steam 与地图下载' {
        foreach ($library in $Libraries) {
            $target = Join-Path $library 'steamapps\workshop\content\730\3086023598'
            if (Test-Path -LiteralPath $target -PathType Container) { $targets.Add($target) }
            foreach ($name in @('appmanifest_730.acf','workshop\appworkshop_730.acf')) {
                $path = Join-Path $library ('steamapps\' + $name)
                if (-not (Test-Path -LiteralPath $path)) { continue }
                $text = [IO.File]::ReadAllText($path)
                if ($name -eq 'appmanifest_730.acf') {
                    foreach ($key in @('buildid','StateFlags','LastUpdated','BytesToDownload','BytesDownloaded')) {
                        $match = [regex]::Match($text, '"'+$key+'"\s*"([^"]*)"')
                        if ($match.Success) { Note ('CS2 ' + $key + '=' + $match.Groups[1].Value) }
                    }
                } else {
                    # Only extract this map's immediate blocks, never account data.
                    $blocks = [regex]::Matches($text, '"3086023598"\s*\{([^{}]*)\}')
                    foreach ($block in $blocks) {
                        foreach ($key in @('manifest','size','timeupdated','timetouched','BytesToDownload','BytesDownloaded','NeedsUpdate','NeedsDownload')) {
                            $match = [regex]::Match($block.Groups[1].Value, '"'+$key+'"\s*"([^"]*)"')
                            if ($match.Success) { Note ('地图下载 ' + $key + '=' + $match.Groups[1].Value) }
                        }
                    }
                }
            }
        }
        Note ('找到地图目录数量：' + $targets.Count)
        if ($targets.Count -eq 0) { Note '未找到 3086023598 的下载目录。' }
    }
    foreach ($target in $targets) {
        Section ('地图 ' + $target) {
            $comparison=$manifest
            $statePath = Join-Path $target '.aim-recoil-patch-backup\state.json'
            $state=$null
            if(Test-Path -LiteralPath $statePath){$state=Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json}
            $dataName='3086023598_002.vpk'
            if((Field $manifest 'adaptive') -and (Field $state 'adaptiveReceipt')){
                $candidate=Field $state 'patchDataFile'
                if($candidate -notmatch '^3086023598_\d{3}\.vpk$'){throw '自适配记录的分卷名称无效。'}
                $comparison=$state;$dataName=$candidate
                Note ('当前按本机自适配记录比对；接入方案='+(Field (Field $state 'adaptiveReceipt') 'plan'))
                Note ('本机原图指纹='+(Field $state 'originalDirSha256'))
            } elseif(Field $manifest 'adaptive') {
                Note '尚无本机自适配记录。下列固定清单仅为历史参照，不能据此断定新版不兼容；运行一键安装可检查脚本接口。'
            }
            foreach ($name in (Field $comparison 'baseVolumes').PSObject.Properties.Name) {
                InspectFile (Join-Path $target $name) (Field (Field $comparison 'baseVolumes') $name)
            }
            foreach ($name in @('3086023598_dir.vpk',$dataName)) { InspectFile (Join-Path $target $name) }
            $installedHash = Get-FileDigest (Join-Path $target '3086023598_dir.vpk')
            $dataHash = Get-FileDigest (Join-Path $target $dataName)
            Note ('目录与所比对补丁匹配=' + ($installedHash -eq (Field $comparison 'patchDirSha256')))
            Note ('新增数据卷与所比对补丁匹配=' + ($dataHash -eq (Field $comparison 'patchDataSha256')))
            Note ('目录为所比对原版=' + ($installedHash -eq (Field $comparison 'originalDirSha256')))
            if (Test-Path -LiteralPath $statePath) {
                $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
                Note ('备份记录版本=' + (Field $state 'version'))
            } else { Note '没有补丁备份记录。' }
        }
    }
    $games = @(); $helpers = @()
    Section '当前运行状态' {
        $processes = @(Get-CimInstance Win32_Process -Filter "Name='cs2.exe' OR Name='5EHubAssist.exe'")
        $script:games = @($processes | Where-Object { $_.Name -eq 'cs2.exe' })
        $script:helpers = @($processes | Where-Object { $_.Name -eq '5EHubAssist.exe' })
        Note ('CS2 进程数量=' + $games.Count + '；辅助程序进程数量=' + $helpers.Count + '（打包程序通常有父、子两个进程）')
        foreach ($game in $games) {
            Note ('本机控制台参数=' + ([string]$game.CommandLine -match '(?i)-vconport\s+29000(?:\s|$)'))
            Note ('本机训练参数=' + ([string]$game.CommandLine -match '(?i)(?:^|\s)-insecure(?:\s|$)'))
            Note ('Vulkan 参数=' + ([string]$game.CommandLine -match '(?i)(?:^|\s)-vulkan(?:\s|$)'))
        }
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 29000 -ErrorAction SilentlyContinue)
        foreach ($listener in $listeners) { Note ('本机控制台监听=' + $listener.LocalAddress + '；PID=' + $listener.OwningProcess) }
        if ($listeners.Count -eq 0) { Note '未发现 29000 端口监听。' }
        foreach ($helper in $helpers) {
            if ($helper.ExecutablePath) { Note ('辅助程序位置=' + $helper.ExecutablePath) }
        }
    }
    Section '轨迹运行报告' {
        $path = Join-Path $env:LOCALAPPDATA '5EHub-Recoil-Patch\view-bridge.json'
        if (-not (Test-Path -LiteralPath $path)) { Note '尚无辅助程序运行报告，无法判断游戏内轨迹开关与状态。'; return }
        $runtime = $null
        for ($attempt = 0; $attempt -lt 3; $attempt++) {
            try { $runtime = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json; break }
            catch { if ($attempt -eq 2) { throw }; Start-Sleep -Milliseconds 100 }
        }
        $age = ([DateTime]::UtcNow - (Get-Item -LiteralPath $path).LastWriteTimeUtc).TotalSeconds
        $fresh = $age -ge 0 -and $age -lt 10 -and $games.Count -gt 0 -and $helpers.Count -gt 0
        Note ('报告距现在秒数=' + [Math]::Round($age,1) + '；满足实时判断条件=' + $fresh)
        Note '不满足实时条件时，以下是历史数据，不能证明当前轨迹状态。render 也可能是上一轮保留的数据。'
        foreach ($key in @('samples','seconds','samplesPerSecond','state','screenShakeSync')) {
            Note ($key + '=' + ((Field $runtime $key) | ConvertTo-Json -Depth 18 -Compress))
        }
        if ($fresh) {
            $state = Field $runtime 'state'
            if (-not $state) { Note '辅助程序运行但未收到地图脚本状态，须检查是否加载了补丁地图。' }
            else {
                if ((Field $state 'mode') -ne 'peek') { Note '当前不是闪身模式，轨迹不会显示。' }
                if (-not (Field $state 'active')) { Note '当前未检测到已开始的训练轮。' }
                if (-not (Field $state 'guide')) { Note '轨迹总开关处于关闭。' }
                if (-not (Field (Field $state 'bot') 'alive')) { Note '当前未检测到存活训练 Bot。' }
                Note ('当前武器=' + (Field $state 'weapon'))
            }
        }
    }
    Section '显卡与系统' {
        foreach ($gpu in @(Get-CimInstance Win32_VideoController)) { Note ('显卡=' + $gpu.Name + '；驱动=' + $gpu.DriverVersion) }
        $os = Get-CimInstance Win32_OperatingSystem
        Note ('系统=' + $os.Caption + '；build=' + $os.BuildNumber)
    }
    Note "`n检查完成。报告只保存在本机，不会自动上传。"
} catch { Note ('检查异常：' + $_.Exception.Message) }
finally {
    try { [IO.File]::WriteAllLines($ReportPath,$rows.ToArray(),(New-Object Text.UTF8Encoding($true))); Write-Host ('报告已保存：' + $ReportPath) -ForegroundColor Green }
    catch {
        try {
            $fallback = Join-Path $env:LOCALAPPDATA '5EHub-Recoil-Diagnostics'
            New-Item -ItemType Directory -Path $fallback -Force | Out-Null
            $fallbackPath = Join-Path $fallback ('5ehub-support-report-' + [DateTime]::Now.ToString('yyyyMMdd-HHmmss') + '.txt')
            [IO.File]::WriteAllLines($fallbackPath,$rows.ToArray(),(New-Object Text.UTF8Encoding($true)))
            Write-Host ('工具文件夹不可写，报告已改存：' + $fallbackPath) -ForegroundColor Yellow
        } catch { Write-Host ('报告保存失败：' + $_.Exception.Message) -ForegroundColor Red; exit 1 }
    }
}
