Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:MapId = '3086023598'
$script:DirName = '3086023598_dir.vpk'
$script:DataName = '3086023598_002.vpk'
$script:PatchPhase = '初始化'

function Throw-PatchIssue([string]$Code, [string]$Message, [string[]]$Details = @(), [string]$Next = '') {
    $error = New-Object System.InvalidOperationException -ArgumentList $Message
    $error.Data['PatchCode'] = $Code
    $error.Data['PatchDetails'] = $Details -join "`n"
    $error.Data['PatchNext'] = $Next
    throw $error
}

function Write-PatchFailure($Failure) {
    $cause = $Failure.Exception
    $code = 'UNKNOWN_ERROR'; $message = $cause.Message
    $details = ''; $next = '请保留命令框完整输出，或运行一键检查后发送报告。'
    while ($null -ne $cause) {
        if ($cause.Data.Contains('PatchCode')) {
            $code = [string]$cause.Data['PatchCode']; $message = $cause.Message
            $details = [string]$cause.Data['PatchDetails']; $next = [string]$cause.Data['PatchNext']; break
        }
        $nativeCode = if ($cause -is [ComponentModel.Win32Exception]) { $cause.NativeErrorCode } else { $cause.HResult -band 65535 }
        if ($cause -is [UnauthorizedAccessException] -or $cause -is [Security.SecurityException] -or $nativeCode -eq 5) {
            $code = 'ACCESS_DENIED'; $message = '访问文件或目录被拒绝。'
            $details = $cause.Message
            $next = '检查文件只读属性、目录权限及安全软件拦截记录；必要时右键当前按钮，以管理员身份运行。'
        } elseif ($cause -is [IO.IOException] -and $nativeCode -in @(32,33)) {
            $code = 'FILE_IN_USE'; $message = '文件正在被其他程序占用。'
            $details = $cause.Message; $next = '退出 CS2，并等 Steam 地图下载或验证结束后重试。不要同时运行两个安装器。'
        } elseif ($cause -is [IO.IOException] -and $nativeCode -in @(39,112)) {
            $code = 'DISK_SPACE_LOW'; $message = '目标磁盘剩余空间不足。'
            $details = $cause.Message; $next = '清理地图所在磁盘的空间后重试。'
        }
        $cause = $cause.InnerException
    }
    if ($code -eq 'UNKNOWN_ERROR' -and $Failure.CategoryInfo.Category -eq 'PermissionDenied') {
        $code = 'ACCESS_DENIED'; $message = '访问被拒绝。'
        $details = $Failure.Exception.Message
        $next = '检查目录权限和安全软件拦截记录；必要时以管理员身份运行。'
    }
    Write-Host "`n操作未完成 [$code]：$message" -ForegroundColor Red
    Write-Host ('发生环节：' + $script:PatchPhase)
    if ($details) { Write-Host $details }
    if ($next) { Write-Host ('处理办法：' + $next) -ForegroundColor Yellow }
}

function Read-PatchManifest([string]$PackageRoot) {
    $path = Join-Path $PackageRoot 'manifest.json'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Throw-PatchIssue 'PACKAGE_FILE_MISSING' '缺少补丁版本清单。' @($path) '请重新完整解压补丁，不要从压缩包内直接运行。'
    }
    $text = [IO.File]::ReadAllText($path)
    try { $manifest = $text | ConvertFrom-Json } catch {
        Throw-PatchIssue 'PACKAGE_MANIFEST_INVALID' '补丁版本清单损坏，无法判断兼容版本。' @($path) '重新下载并完整解压补丁。'
    }
    foreach ($key in @('schema','mapId','version','baseVolumes','originalDirSha256','patchDirSha256','patchDataSha256')) {
        if (-not $manifest -or -not $manifest.PSObject.Properties[$key]) {
            Throw-PatchIssue 'PACKAGE_MANIFEST_INVALID' '补丁版本清单缺少必要信息。' @('缺少：' + $key) '重新下载并完整解压补丁。'
        }
    }
    if ($manifest.schema -ne 1 -or $manifest.mapId -ne $script:MapId) {
        Throw-PatchIssue 'PACKAGE_MANIFEST_INVALID' '补丁清单格式或地图编号不符。' @() '请使用 5EHub 对应的完整补丁包。'
    }
    foreach ($key in @('originalDirSha256','patchDirSha256','patchDataSha256')) {
        if ($manifest.PSObject.Properties[$key].Value -notmatch '^[0-9a-fA-F]{64}$') {
            Throw-PatchIssue 'PACKAGE_MANIFEST_INVALID' '补丁版本清单的文件校验信息无效。' @($key) '重新下载完整补丁，不要手动修改校验值。'
        }
    }
    if ($manifest.PSObject.Properties['helper'] -and (-not $manifest.helper -or -not $manifest.helper.PSObject.Properties['sha256'] -or $manifest.helper.sha256 -notmatch '^[0-9a-fA-F]{64}$')) {
        Throw-PatchIssue 'PACKAGE_MANIFEST_INVALID' '补丁版本清单缺少有效的辅助程序校验信息。' @() '重新下载并完整解压补丁。'
    }
    return $manifest
}

function Find-KnownBaseline($Manifest, $Hashes) {
    if (-not $Manifest.PSObject.Properties['knownMaps']) { return $null }
    foreach ($record in $Manifest.knownMaps) {
        if (-not $record.PSObject.Properties['baseVolumes']) { continue }
        $matches = $true
        foreach ($name in @('3086023598_000.vpk','3086023598_001.vpk')) {
            if (-not $record.baseVolumes.PSObject.Properties[$name] -or $Hashes[$name] -ne $record.baseVolumes.PSObject.Properties[$name].Value) { $matches = $false }
        }
        if ($matches) { return $record }
    }
    return $null
}

function Assert-MapBaseline([string]$Target, $Manifest) {
    $script:PatchPhase = '原地图下载与版本检查'
    $missing = @()
    foreach ($name in @($script:DirName,'3086023598_000.vpk','3086023598_001.vpk')) {
        $path = Join-Path $Target $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { $missing += '缺少文件：' + $path }
        elseif ((Get-Item -LiteralPath $path).Length -eq 0) { $missing += '空文件：' + $path }
    }
    if ($missing.Count -gt 0) {
        Throw-PatchIssue 'MAP_DOWNLOAD_INCOMPLETE' '原地图文件缺失或为空。' $missing '先等待 Steam 创意工坊下载全部完成；仍缺失时重新订阅 5EHub。'
    }
    $actual = @{}; $expected = @{}; $different = @()
    foreach ($name in @('3086023598_000.vpk','3086023598_001.vpk')) {
        $item = $Manifest.baseVolumes.PSObject.Properties[$name]
        if (-not $item -or $item.Value -notmatch '^[0-9a-fA-F]{64}$') {
            Throw-PatchIssue 'PACKAGE_MANIFEST_INVALID' '补丁清单缺少有效的地图版本信息。' @($name) '重新下载完整补丁。'
        }
        $expected[$name] = $item.Value
        $actual[$name] = Get-FileDigest (Join-Path $Target $name)
        if ($actual[$name] -ne $expected[$name]) {
            $different += "文件内容不匹配：$name`n需要的 SHA256：$($expected[$name])`n实际的 SHA256：$($actual[$name])"
        }
    }
    $supported = Find-KnownBaseline $Manifest $expected
    $installed = Find-KnownBaseline $Manifest $actual
    $supportedLabel = if ($supported) { $supported.label } else { '本包清单对应的原地图版本' }
    Write-Host ('本补丁支持：' + $supportedLabel)
    if ($different.Count -eq 0) { Write-Host '原地图版本：匹配。' -ForegroundColor Green; return }
    if ($installed) {
        $details = @("当前地图：$($installed.label)", "本补丁支持：$supportedLabel") + $different
        if ($supported -and $installed.date -gt $supported.date) {
            Throw-PatchIssue 'PATCH_OUTDATED' '补丁版本过旧，不能用于当前新版地图。' $details '使用适配当前地图的新版补丁；重新下载原地图或提升权限不能让旧补丁兼容新版。'
        }
        if ($supported -and $installed.date -lt $supported.date) {
            Throw-PatchIssue 'MAP_OUTDATED' '当前原地图为旧版，与本补丁支持的版本不同。' $details '先在 Steam 更新或重新订阅原版 5EHub，下载完成后再安装。'
        }
        Throw-PatchIssue 'MAP_VERSION_UNSUPPORTED' '当前地图版本不在本补丁支持范围内。' $details '使用对应地图版本的补丁，并保留以上版本信息。'
    }
    Throw-PatchIssue 'MAP_CONTENT_MISMATCH' '原地图文件内容不匹配，尚不能确定是新版本还是文件损坏。' $different '原版能正常游玩时，发送以上信息以适配该版本；原版也无法加载时，先检查 Steam 下载是否完成。'
}

function Get-FileDigest([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return '' }
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}

function Assert-Digest([string]$Path, [string]$Expected, [string]$Role = 'File') {
    if ($Expected -notmatch '^[0-9a-fA-F]{64}$') {
        Throw-PatchIssue 'PACKAGE_MANIFEST_INVALID' '缺少有效的文件校验信息。' @($Path) '重新下载完整补丁。'
    }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        $code = switch ($Role) { 'Package' { 'PACKAGE_FILE_MISSING' } 'Backup' { 'BACKUP_MISSING' } 'Installed' { 'PATCH_NOT_INSTALLED' } default { 'FILE_MISSING' } }
        $next = switch ($Role) {
            'Package' { '重新完整解压补丁，不要直接从压缩包运行；辅助程序缺失时也检查安全软件的拦截记录。' }
            'Backup' { '保留当前文件并发送完整错误信息，不要强行覆盖或还原。' }
            'Installed' { '先退出 CS2，运行同一补丁文件夹内的一键安装，再使用启动训练。' }
            default { '保留完整错误信息，并运行一键检查。' }
        }
        Throw-PatchIssue $code '缺少文件，无法继续。' @($Path) $next
    }
    $actual = Get-FileDigest $Path
    if ($actual -ne $Expected) {
        $code = switch ($Role) { 'Package' { 'PACKAGE_CORRUPT' } 'Backup' { 'BACKUP_CORRUPT' } 'Installed' { 'PATCH_NOT_INSTALLED' } default { 'FILE_CONTENT_MISMATCH' } }
        $next = switch ($Role) {
            'Package' { '重新下载并完整解压补丁，不要混用不同版本的文件。' }
            'Backup' { '备份内容不同，已停止覆盖；保留现有文件并发送完整错误信息。' }
            'Installed' { '地图可能被 Steam 更新覆盖，或安装的是另一版补丁；退出 CS2 后重新运行当前补丁的一键安装。' }
            default { '保留完整错误信息，并运行一键检查。' }
        }
        Throw-PatchIssue $code '文件内容不匹配，无法继续。' @($Path, "需要的 SHA256：$Expected", "实际的 SHA256：$actual") $next
    }
}

function Get-SteamLibraries {
    $roots = New-Object 'System.Collections.Generic.List[string]'
    foreach ($item in @(
        @('HKCU:\Software\Valve\Steam', 'SteamPath'),
        @('HKLM:\SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'),
        @('HKLM:\SOFTWARE\Valve\Steam', 'InstallPath')
    )) {
        $reg = Get-ItemProperty -LiteralPath $item[0] -ErrorAction SilentlyContinue
        if ($reg -and $reg.PSObject.Properties[$item[1]]) {
            $value = [string]$reg.PSObject.Properties[$item[1]].Value
            if ($value -and -not $roots.Contains($value)) { $roots.Add($value) }
        }
    }
    $fallback = Join-Path ${env:ProgramFiles(x86)} 'Steam'
    if ((Test-Path -LiteralPath $fallback) -and -not $roots.Contains($fallback)) { $roots.Add($fallback) }
    foreach ($root in @($roots.ToArray())) {
        $vdf = Join-Path $root 'steamapps\libraryfolders.vdf'
        if (-not (Test-Path -LiteralPath $vdf)) { continue }
        $text = [IO.File]::ReadAllText($vdf)
        foreach ($match in [regex]::Matches($text, '"path"\s+"((?:\\.|[^"\\])*)"')) {
            $path = $match.Groups[1].Value.Replace('\\', '\').Replace('\"', '"')
            if (-not $roots.Contains($path)) { $roots.Add($path) }
        }
    }
    $unique = @()
    foreach ($root in $roots) {
        $path = [IO.Path]::GetFullPath($root).TrimEnd([char]'\')
        if ($unique -notcontains $path) { $unique += $path }
    }
    return $unique
}

function Find-MapTargets([string[]]$Libraries) {
    foreach ($library in $Libraries) {
        $path = Join-Path $library "steamapps\workshop\content\730\$script:MapId"
        if (Test-Path -LiteralPath $path -PathType Container) {
            (Get-Item -LiteralPath $path).FullName
        }
    }
}

function Resolve-MapTarget([string]$TargetPath) {
    if (-not $TargetPath) {
        $targets = @(Find-MapTargets @(Get-SteamLibraries) | Sort-Object -Unique)
        if ($targets.Count -eq 1) { $TargetPath = $targets[0] }
        elseif ($targets.Count -gt 1) {
            for ($i = 0; $i -lt $targets.Count; $i++) { Write-Host ("{0}. {1}" -f ($i + 1), $targets[$i]) }
            $number = 0
            if (-not [int]::TryParse((Read-Host '找到多份 5EHub，请输入要安装的序号'), [ref]$number) -or $number -lt 1 -or $number -gt $targets.Count) {
                throw '未选择有效的地图目录。'
            }
            $TargetPath = $targets[$number - 1]
        }
        else { Throw-PatchIssue 'MAP_NOT_FOUND' '未找到 5EHub 下载目录。' @() '请在 Steam 订阅 5EHub（3086023598），并等待下载完成。' }
    }
    if (-not (Test-Path -LiteralPath $TargetPath -PathType Container)) {
        Throw-PatchIssue 'MAP_PATH_MISSING' '指定的地图目录不存在。' @($TargetPath) '先确认 Steam 已下载 5EHub，或选择正确的地图目录。'
    }
    $target = (Get-Item -LiteralPath $TargetPath -ErrorAction Stop).FullName
    if ((Split-Path $target -Leaf) -ne $script:MapId -or (Split-Path (Split-Path $target -Parent) -Leaf) -ne '730') {
        Throw-PatchIssue 'MAP_PATH_INVALID' '选择的目录不是 5EHub 创意工坊目录。' @($target) '请选择 Steam 创意工坊的 730\3086023598 目录。'
    }
    return $target
}

function Assert-GameClosed {
    if (@(Get-Process -Name cs2 -ErrorAction SilentlyContinue).Count -gt 0) {
        Throw-PatchIssue 'GAME_RUNNING' 'CS2 正在运行，暂时不能安装或还原。' @() '完全退出 CS2 后，重新运行安装或还原。'
    }
}

function Assert-PatchWriteAccess([string]$Target, [string[]]$Files, [long]$RequiredBytes) {
    $script:PatchPhase = '磁盘空间与写入权限检查'
    $root = [IO.Path]::GetPathRoot($Target)
    if ($root -match '^[A-Za-z]:\\$') {
        $drive = New-Object IO.DriveInfo -ArgumentList $root
        if ($drive.AvailableFreeSpace -lt $RequiredBytes) {
            Throw-PatchIssue 'DISK_SPACE_LOW' '目标磁盘不足以保留备份和安装临时文件。' @("磁盘：$root", "需要预留字节：$RequiredBytes", "剩余字节：$($drive.AvailableFreeSpace)") '清理地图所在磁盘的空间后重试。'
        }
    }
    foreach ($path in $Files) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $handle = [IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
            $handle.Dispose()
        }
    }
    # Probe creation/deletion before changing any map file. This leaves no file.
    $probe = Join-Path $Target ('.aim-recoil-write-check-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $handle = New-Object IO.FileStream -ArgumentList @($probe,[IO.FileMode]::CreateNew,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None,4096,[IO.FileOptions]::DeleteOnClose)
    $handle.Dispose()
    Write-Host '空间、文件占用及写入权限检查通过。' -ForegroundColor Green
}

function Write-JsonFile([string]$Path, $Value) {
    $Value | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Remove-Stage([string]$Target, [string]$Stage) {
    $resolved = [IO.Path]::GetFullPath($Stage)
    $parent = [IO.Path]::GetDirectoryName($resolved)
    if ($parent -ne $Target -or -not ([IO.Path]::GetFileName($resolved).StartsWith('.aim-recoil-stage-'))) {
        throw '临时目录路径校验失败，未删除任何内容。'
    }
    if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}

function Invoke-MapPatch([string]$PackageRoot, [string]$TargetPath, [string]$Action = 'Install') {
    $script:PatchPhase = '补丁包完整性检查'
    Write-Host '[1/5] 检查补丁包完整性……'
    $manifest = Read-PatchManifest $PackageRoot
    Write-Host ('补丁版本：' + $manifest.version)
    if ($Action -eq 'Install' -and $manifest.PSObject.Properties['helper']) {
        Assert-Digest (Join-Path $PackageRoot 'helper\5EHubAssist.exe') $manifest.helper.sha256 'Package'
    }
    $payload = Join-Path $PackageRoot 'payload'
    Assert-Digest (Join-Path $payload $script:DirName) $manifest.patchDirSha256 'Package'
    Assert-Digest (Join-Path $payload $script:DataName) $manifest.patchDataSha256 'Package'
    $reference = Join-Path $PackageRoot 'reference\3086023598_dir.vpk'
    Assert-Digest $reference $manifest.originalDirSha256 'Package'
    $script:PatchPhase = '定位原地图'
    Write-Host '[2/5] 查找 5EHub 地图目录……'
    $target = Resolve-MapTarget $TargetPath
    Write-Host ('地图目录：' + $target)
    Write-Host '[3/5] 检查原地图下载与版本兼容性……'
    Assert-MapBaseline $target $manifest
    $script:PatchPhase = '备份与旧补丁检查'
    Write-Host '[4/5] 检查备份、已安装版本及旧文件残留……'
    $directory = Join-Path $target $script:DirName
    $data = Join-Path $target $script:DataName
    $backup = Join-Path $target '.aim-recoil-patch-backup'
    $statePath = Join-Path $backup 'state.json'
    $dirHash = Get-FileDigest $directory
    $dataHash = Get-FileDigest $data
    $rebase = $false
    $previousMaps = @()
    if ($manifest.PSObject.Properties['previousMaps']) { $previousMaps = @($manifest.previousMaps) }
    $state = $null
    if (Test-Path -LiteralPath $statePath) {
        $stateText = [IO.File]::ReadAllText($statePath)
        try { $state = $stateText | ConvertFrom-Json } catch {
            Throw-PatchIssue 'BACKUP_MANIFEST_INVALID' '备份记录损坏，无法确认原地图版本。' @($statePath) '保留备份并发送完整错误信息，不要直接删除备份或强行还原。'
        }
        foreach ($key in @('schema','originalDirSha256','patchDirSha256','patchDataSha256')) {
            if (-not $state -or -not $state.PSObject.Properties[$key]) {
                Throw-PatchIssue 'BACKUP_MANIFEST_INVALID' '备份记录缺少必要信息。' @('缺少：' + $key) '保留备份并发送完整错误信息。'
            }
        }
        if ($state.schema -ne 1) { Throw-PatchIssue 'BACKUP_MANIFEST_INVALID' '备份格式无法识别。' @($statePath) '保留备份并发送错误信息。' }
        if ($state.originalDirSha256 -ne $manifest.originalDirSha256) {
            $known = @($previousMaps | Where-Object { $_.originalDirSha256 -eq $state.originalDirSha256 })
            if ($known.Count -ne 1 -or $dirHash -ne $manifest.originalDirSha256) {
                Throw-PatchIssue 'BACKUP_VERSION_UNSUPPORTED' '备份属于其他地图版本，当前条件不能安全迁移。' @("备份原图校验：$($state.originalDirSha256)", "本包原图校验：$($manifest.originalDirSha256)") '保留备份并发送完整错误信息，使用对应版本的补丁；不要删除备份或强行覆盖。'
            }
            $pair = @($known[0].patches | Where-Object { $_.patchDirSha256 -eq $state.patchDirSha256 -and $_.patchDataSha256 -eq $state.patchDataSha256 })
            if ($pair.Count -ne 1) { Throw-PatchIssue 'BACKUP_PATCH_UNKNOWN' '旧备份中的补丁版本无法识别。' @($statePath) '保留旧备份并发送完整错误信息，不要强行覆盖。' }
            Assert-Digest (Join-Path $backup $script:DirName) $known[0].originalDirSha256 'Backup'
            $rebase = $true
            Write-Host '检测到重新订阅后留下的已识别旧备份；安装时会归档并为新版原地图建立备份。' -ForegroundColor Yellow
        } else { Assert-Digest (Join-Path $backup $script:DirName) $manifest.originalDirSha256 'Backup' }
    }
    $allowedDirs = @($manifest.originalDirSha256, $manifest.patchDirSha256)
    $allowedData = @('', $manifest.patchDataSha256)
    if ($state -and -not $rebase) { $allowedDirs += $state.patchDirSha256; $allowedData += $state.patchDataSha256 }
    # Steam replaces the original volumes but leaves our added volume behind.
    # Accept only published, known residue alongside the verified new original dir.
    if ($dirHash -eq $manifest.originalDirSha256) {
        foreach ($previous in $previousMaps) { foreach ($patch in $previous.patches) { $allowedData += $patch.patchDataSha256 } }
    }
    if ($dirHash -notin $allowedDirs) {
        Throw-PatchIssue 'MAP_DIRECTORY_UNKNOWN' '地图目录卷存在未识别的版本或修改。' @("文件：$directory", "实际 SHA256：$dirHash") '保留现有文件并发送完整错误信息，不要直接覆盖其他修改。'
    }
    if ($dirHash -ne $manifest.originalDirSha256 -and -not $dataHash) {
        Throw-PatchIssue 'PATCH_DATA_MISSING' '已安装补丁的新增数据卷缺失。' @($data) '请保留备份并发送错误信息；不要混用其他版本的数据卷。'
    }
    if (($state -and $dirHash -eq $state.patchDirSha256 -and $dataHash -ne $state.patchDataSha256) -or ($dirHash -eq $manifest.patchDirSha256 -and $dataHash -ne $manifest.patchDataSha256)) {
        Throw-PatchIssue 'PATCH_PAIR_MISMATCH' '补丁目录卷和新增数据卷不是配套版本。' @("目录 SHA256：$dirHash", "数据 SHA256：$dataHash") '保留备份并发送完整错误信息；请使用同一个完整补丁包，不要混用文件。'
    }
    if ($dataHash -notin $allowedData) {
        Throw-PatchIssue 'PATCH_RESIDUE_UNKNOWN' '发现无法识别的新增数据卷，不能判断是否属于本补丁。' @($data, '实际 SHA256：' + $dataHash) '保留该文件并发送完整错误信息，不要强行删除或覆盖。'
    }
    if ($dirHash -eq $manifest.originalDirSha256 -and $dataHash -and $dataHash -ne $manifest.patchDataSha256) {
        Write-Host '发现已识别的旧补丁数据残留；本次操作可以处理，无需手动删除。' -ForegroundColor Yellow
    }
    $script:PatchPhase = '安装条件检查'
    Write-Host '[5/5] 检查安装条件……'
    if ($Action -eq 'Check') {
        Write-Host "校验通过：$target"
        Write-Host '仅检查已结束，未试写文件；实际安装时仍会检查游戏占用和写入权限。'
        return
    }
    Assert-GameClosed
    $reserve = (Get-Item -LiteralPath (Join-Path $payload $script:DataName)).Length * 2 + 1048576
    if ($dataHash) { $reserve += (Get-Item -LiteralPath $data).Length }
    Assert-PatchWriteAccess $target @($directory,$data,(Join-Path $backup $script:DirName),$statePath) $reserve
    Write-Host '预检通过，开始操作。' -ForegroundColor Green
    $script:PatchPhase = '写入地图及备份（失败时尝试回滚）'
    Write-Host "地图：$target"
    $lockPath = Join-Path $target '.aim-recoil-patch.lock'
    $lock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $stage = Join-Path $target ('.aim-recoil-stage-' + [Guid]::NewGuid().ToString('N'))
    try {
        New-Item -ItemType Directory -Path $stage | Out-Null
        # Capture the files we may change. The original map volumes are read-only.
        Copy-Item -LiteralPath $directory -Destination (Join-Path $stage 'previous-dir.vpk')
        if ($dataHash) { Copy-Item -LiteralPath $data -Destination (Join-Path $stage 'previous-data.vpk') }
        if ($state) { Copy-Item -LiteralPath $statePath -Destination (Join-Path $stage 'previous-state.json') }
        if ($rebase) { Copy-Item -LiteralPath (Join-Path $backup $script:DirName) -Destination (Join-Path $stage 'previous-original.vpk') }
        $changing = $false
        $backupChanging = $false
        try {
            if (-not $state -or $rebase) {
                $original = if ($dirHash -eq $manifest.originalDirSha256) { $directory } else { $reference }
                Copy-Item -LiteralPath $original -Destination (Join-Path $stage 'next-original.vpk')
                Assert-Digest (Join-Path $stage 'next-original.vpk') $manifest.originalDirSha256
                New-Item -ItemType Directory -Path $backup -Force | Out-Null
                if ($rebase) {
                    $history = Join-Path $backup ('history\' + [Guid]::NewGuid().ToString('N'))
                    New-Item -ItemType Directory -Path $history | Out-Null
                    Copy-Item -LiteralPath (Join-Path $stage 'previous-original.vpk') -Destination (Join-Path $history $script:DirName)
                    Copy-Item -LiteralPath (Join-Path $stage 'previous-state.json') -Destination (Join-Path $history 'state.json')
                    Assert-Digest (Join-Path $history $script:DirName) $state.originalDirSha256
                }
                $backupChanging = $true
                Copy-Item -LiteralPath (Join-Path $stage 'next-original.vpk') -Destination (Join-Path $backup $script:DirName)
                Assert-Digest (Join-Path $backup $script:DirName) $manifest.originalDirSha256
            }
            if ($Action -eq 'Install') {
                Copy-Item -LiteralPath (Join-Path $payload $script:DataName) -Destination (Join-Path $stage 'next-data.vpk')
                Copy-Item -LiteralPath (Join-Path $payload $script:DirName) -Destination (Join-Path $stage 'next-dir.vpk')
                Assert-Digest (Join-Path $stage 'next-data.vpk') $manifest.patchDataSha256
                Assert-Digest (Join-Path $stage 'next-dir.vpk') $manifest.patchDirSha256
                $changing = $true
                Copy-Item -LiteralPath (Join-Path $stage 'next-data.vpk') -Destination $data
                Copy-Item -LiteralPath (Join-Path $stage 'next-dir.vpk') -Destination $directory
                Assert-Digest $data $manifest.patchDataSha256
                Assert-Digest $directory $manifest.patchDirSha256
                $nextState = @{schema=1; version=$manifest.version; originalDirSha256=$manifest.originalDirSha256; patchDirSha256=$manifest.patchDirSha256; patchDataSha256=$manifest.patchDataSha256; installed=$true}
            }
            elseif ($Action -eq 'Restore') {
                $changing = $true
                Copy-Item -LiteralPath (Join-Path $backup $script:DirName) -Destination $directory
                Assert-Digest $directory $manifest.originalDirSha256
                if ($dataHash) { Remove-Item -LiteralPath $data -Force }
                $nextState = if ($state -and -not $rebase) { $state } else { @{schema=1; version=$manifest.version; originalDirSha256=$manifest.originalDirSha256; patchDirSha256=$manifest.patchDirSha256; patchDataSha256=$manifest.patchDataSha256} }
                $nextState.installed = $false
            }
            else { throw '未知操作。' }
            Write-JsonFile (Join-Path $stage 'next-state.json') $nextState
            Copy-Item -LiteralPath (Join-Path $stage 'next-state.json') -Destination $statePath
        }
        catch {
            if ($rebase -and $backupChanging) { Copy-Item -LiteralPath (Join-Path $stage 'previous-original.vpk') -Destination (Join-Path $backup $script:DirName) }
            if ($changing) {
                Copy-Item -LiteralPath (Join-Path $stage 'previous-dir.vpk') -Destination $directory
                if ($dataHash) { Copy-Item -LiteralPath (Join-Path $stage 'previous-data.vpk') -Destination $data }
                elseif (Test-Path -LiteralPath $data) { Remove-Item -LiteralPath $data -Force }
            }
            if ($state) { Copy-Item -LiteralPath (Join-Path $stage 'previous-state.json') -Destination $statePath }
            elseif (Test-Path -LiteralPath $statePath) { Remove-Item -LiteralPath $statePath -Force }
            throw
        }
        if ($Action -eq 'Install') {
            if ($rebase) { Write-Host '已适配重新订阅后的新版地图。旧备份已存入 history，一键还原将恢复新版原地图。' }
            Write-Host '安装完成。请双击本文件夹中的“启动训练.cmd”。' -ForegroundColor Green
            Write-Host '双 Tab → 自瞄与目标：绘制切换、显示时机、选择武器、屏幕晃动。自瞄默认关闭。'
            Write-Host '第一版绘制需选择匹配的分辨率；第二版绘制由游戏引擎投影。'
        }
        else { Write-Host '已恢复原版 5EHub，备份仍保留。' -ForegroundColor Green }
    }
    finally {
        try { Remove-Stage $target $stage }
        finally { $lock.Dispose(); Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue }
    }
}
